import hashlib
from io import BytesIO

import pytest
from werkzeug.datastructures import FileStorage

from municipal_diagnostico.extensions import db
from municipal_diagnostico.iso45001_seed_data import (
    ISO45001_V2_CATALOG_SLUG,
    ISO45001_V3_CATALOG_SLUG,
)
from municipal_diagnostico.models import (
    Iso45001CambioCaptura,
    Iso45001CuestionarioVersion,
    Iso45001Evaluacion,
    Iso45001EvaluacionSnapshotCierre,
    Iso45001ReactivoCrosswalk,
    Iso45001Respuesta,
    Usuario,
)
from municipal_diagnostico.services.iso45001 import (
    ISO45001_OPTION_POINTS,
    bulk_apply_document_control_points,
    bulk_apply_section_responses,
    ensure_document_controls_for_evaluation,
    freeze_iso45001_snapshot,
    save_document_control_payload,
    summarize_iso45001_evaluation,
    upload_document_evidence,
)
from municipal_diagnostico.timeutils import utcnow
from tests.test_iso45001_flow import (
    build_app,
    create_iso45001_evaluation,
    reactives_for_version,
)


def _create_v3_evaluation(ids: dict, *, cycle_name: str) -> int:
    return create_iso45001_evaluation(
        ids["dependency_one_id"],
        ids["evaluator_id"],
        ids["reviewer_id"],
        ids["admin_id"],
        cycle_name=cycle_name,
        version_slug=ISO45001_V3_CATALOG_SLUG,
    )


def test_iso45001_v3_catalog_preserves_measurements_and_traceability():
    app, _ids = build_app()

    with app.app_context():
        v2 = Iso45001CuestionarioVersion.query.filter_by(
            slug=ISO45001_V2_CATALOG_SLUG
        ).one()
        v3 = Iso45001CuestionarioVersion.query.filter_by(
            slug=ISO45001_V3_CATALOG_SLUG
        ).one()
        reactives = reactives_for_version(v3)
        sections = [section for clause in v3.clausulas for section in clause.apartados]
        controls = list(v3.controles_evidencia)
        points = [point for control in controls for point in control.puntos]

        assert v3.capture_mode == "agrupado_apartado"
        assert v3.document_coverage_mode == "por_control_punto"
        assert v3.scoring_scheme == "escala_0_1_2_v1"
        assert len(v3.catalog_hash) == 64
        assert len(reactives) == 308
        assert len(sections) == 40
        assert len({reactive.variable_principal for reactive in reactives}) == 39
        assert len(controls) == 37
        assert len(points) == 102

        point_mapped_codes = {
            reactive.codigo
            for point in points
            for reactive in point.reactivos
        }
        assert len(point_mapped_codes) == 266
        assert point_mapped_codes == {
            reactive.codigo
            for reactive in reactives
            if reactive.puntos_evidencia
        }

        reactives_by_code = {reactive.codigo: reactive for reactive in reactives}
        expected_overlaps = {
            "R-250": {"D-23", "D-24"},
            "R-270": {"D-26", "D-27"},
            "R-298": {"D-29", "D-30"},
        }
        for reactive_code, expected_controls in expected_overlaps.items():
            assert {
                point.control.codigo
                for point in reactives_by_code[reactive_code].puntos_evidencia
            } == expected_controls

        amendments = {
            reactive.codigo
            for reactive in reactives
            if reactive.es_enmienda_2024
        }
        assert amendments == {"R-307", "R-308"}

        crosswalk = Iso45001ReactivoCrosswalk.query.filter_by(
            version_origen_id=v2.id,
            version_destino_id=v3.id,
        ).all()
        assert len(crosswalk) == 308
        assert len({row.reactivo_origen_id for row in crosswalk}) == 308
        assert len({row.reactivo_destino_id for row in crosswalk}) == 308
        assert all(
            row.reactivo_origen.codigo == row.reactivo_destino.codigo
            and row.reactivo_destino.identidad_externa
            == (ISO45001_V3_CATALOG_SLUG, row.reactivo_destino.codigo)
            for row in crosswalk
        )


def test_iso45001_v3_bulk_section_modes_create_per_reactive_audit_events():
    app, ids = build_app()

    with app.app_context():
        evaluation_id = _create_v3_evaluation(ids, cycle_name="V3 captura masiva")
        evaluation = db.session.get(Iso45001Evaluacion, evaluation_id)
        user = db.session.get(Usuario, ids["evaluator_id"])
        section = evaluation.ciclo.version.clausulas[0].apartados[0]
        first_reactive = section.reactivos[0]
        db.session.add(
            Iso45001Respuesta(
                evaluacion=evaluation,
                reactivo=first_reactive,
                usuario=user,
                calificacion="no",
                valor=0,
                origen_captura="individual",
            )
        )
        db.session.flush()

        pending = bulk_apply_section_responses(
            evaluation,
            section.id,
            "si",
            "pendientes",
            user=user,
        )
        assert pending["ok"] is True
        assert pending["updated"] == len(section.reactivos) - 1
        assert pending["skipped"] == 1
        responses = {response.reactivo_id: response for response in evaluation.respuestas}
        assert responses[first_reactive.id].calificacion == "no"
        assert all(
            response.calificacion == "si"
            for reactive_id, response in responses.items()
            if reactive_id != first_reactive.id
        )

        no_op = bulk_apply_section_responses(
            evaluation,
            section.id,
            "no",
            "pendientes",
            user=user,
        )
        assert no_op["updated"] == 0
        assert no_op["skipped"] == len(section.reactivos)

        replacement = bulk_apply_section_responses(
            evaluation,
            section.id,
            "parcial",
            "reemplazar",
            user=user,
        )
        assert replacement["ok"] is True
        assert replacement["updated"] == len(section.reactivos)
        assert replacement["skipped"] == 0
        assert all(response.calificacion == "parcial" for response in evaluation.respuestas)
        assert all(response.valor == 1 for response in evaluation.respuestas)
        assert all(response.origen_captura == "masivo" for response in evaluation.respuestas)
        assert {
            response.lote_captura for response in evaluation.respuestas
        } == {replacement["batch_id"]}

        events = Iso45001CambioCaptura.query.filter_by(
            evaluacion_id=evaluation.id,
            entidad_tipo="reactivo",
        ).all()
        assert len(events) == (len(section.reactivos) - 1) + len(section.reactivos)
        assert all(event.origen == "masivo" for event in events)
        assert sum(event.lote_id == pending["batch_id"] for event in events) == len(
            section.reactivos
        ) - 1
        assert sum(event.lote_id == replacement["batch_id"] for event in events) == len(
            section.reactivos
        )


def test_iso45001_v3_individual_and_bulk_scoring_are_equivalent_at_scale_extremes():
    app, ids = build_app()

    with app.app_context():
        user = db.session.get(Usuario, ids["evaluator_id"])
        for index, (rating, expected_percent) in enumerate(
            (("no", 0.0), ("parcial", 50.0), ("si", 100.0)),
            start=1,
        ):
            bulk_id = _create_v3_evaluation(
                ids,
                cycle_name=f"V3 extremo masivo {index}",
            )
            bulk_evaluation = db.session.get(Iso45001Evaluacion, bulk_id)
            for clause in bulk_evaluation.ciclo.version.clausulas:
                for section in clause.apartados:
                    result = bulk_apply_section_responses(
                        bulk_evaluation,
                        section.id,
                        rating,
                        "pendientes",
                        user=user,
                    )
                    assert result["ok"] is True

            individual_id = _create_v3_evaluation(
                ids,
                cycle_name=f"V3 extremo individual {index}",
            )
            individual_evaluation = db.session.get(Iso45001Evaluacion, individual_id)
            for reactive in reactives_for_version(individual_evaluation.ciclo.version):
                db.session.add(
                    Iso45001Respuesta(
                        evaluacion=individual_evaluation,
                        reactivo=reactive,
                        usuario=user,
                        calificacion=rating,
                        valor=ISO45001_OPTION_POINTS[rating],
                        origen_captura="individual",
                    )
                )
            db.session.flush()

            bulk_summary = summarize_iso45001_evaluation(bulk_evaluation)
            individual_summary = summarize_iso45001_evaluation(individual_evaluation)
            assert bulk_summary["answered_questions"] == 308
            assert individual_summary["answered_questions"] == 308
            assert bulk_summary["points"] == individual_summary["points"]
            assert bulk_summary["percent"] == expected_percent
            assert individual_summary["percent"] == expected_percent


def test_iso45001_v3_bulk_document_points_and_exact_file_coverage(tmp_path):
    app, ids = build_app(tmp_path)

    with app.app_context():
        evaluation_id = _create_v3_evaluation(ids, cycle_name="V3 cobertura por punto")
        evaluation = db.session.get(Iso45001Evaluacion, evaluation_id)
        user = db.session.get(Usuario, ids["evaluator_id"])
        assessment = next(
            item
            for item in ensure_document_controls_for_evaluation(evaluation, user=user)
            if item.control.codigo == "D-01"
        )
        point_responses = sorted(assessment.puntos, key=lambda item: item.punto.orden)
        assert len(point_responses) >= 2
        point_responses[0].evaluado = True
        point_responses[0].cubierto = False
        point_responses[0].origen_captura = "individual"
        db.session.flush()

        pending = bulk_apply_document_control_points(
            evaluation,
            assessment.id,
            True,
            "pendientes",
            user=user,
        )
        assert pending["updated"] == len(point_responses) - 1
        assert pending["skipped"] == 1
        assert point_responses[0].cubierto is False
        assert all(response.cubierto for response in point_responses[1:])

        replacement = bulk_apply_document_control_points(
            evaluation,
            assessment.id,
            False,
            "reemplazar",
            user=user,
        )
        assert replacement["updated"] == len(point_responses)
        assert all(response.evaluado for response in point_responses)
        assert all(not response.cubierto for response in point_responses)
        assert all(response.origen_captura == "masivo" for response in point_responses)

        first_point = point_responses[0].punto
        second_point = point_responses[1].punto
        selected = save_document_control_payload(
            evaluation,
            assessment.id,
            {
                "punto_ids": [first_point.id],
                "evidencia_ids": [],
                "observacion": "Primer punto cubierto tras la aplicación masiva.",
            },
            user=user,
        )
        assert selected["ok"] is True
        assert point_responses[0].origen_captura == "excepcion"

        file_bytes = b"evidencia ISO 45001 v3 por punto"
        uploaded = upload_document_evidence(
            evaluation,
            [
                FileStorage(
                    stream=BytesIO(file_bytes),
                    filename="evidencia-v3.pdf",
                    content_type="application/pdf",
                )
            ],
            [assessment.id],
            user=user,
        )
        assert uploaded["ok"] is True
        evidence = uploaded["evidences"][0]
        assert evidence.sha256 == hashlib.sha256(file_bytes).hexdigest()

        exact_link = save_document_control_payload(
            evaluation,
            assessment.id,
            {
                "punto_ids": [first_point.id, second_point.id],
                "evidencia_ids": [evidence.id],
                "evidencia_punto_ids": [f"{evidence.id}:{first_point.id}"],
                "observacion": "El archivo sustenta únicamente el primer punto.",
            },
            user=user,
        )
        assert exact_link["ok"] is True
        assert {response.punto.id for response in evidence.puntos} == {first_point.id}
        assert point_responses[1].origen_captura == "excepcion"

        summary = summarize_iso45001_evaluation(evaluation)
        control_summary = next(
            control
            for control in summary["document_controls"]
            if control["codigo"] == "D-01"
        )
        first_summary = next(
            point for point in control_summary["puntos"] if point["id"] == first_point.id
        )
        second_summary = next(
            point for point in control_summary["puntos"] if point["id"] == second_point.id
        )
        assert control_summary["evaluated"] is True
        assert first_summary["evidence_ids"] == [evidence.id]
        assert second_summary["evidence_ids"] == []
        assert {row["codigo"] for row in first_summary["reactivos"]} == {
            reactive.codigo for reactive in first_point.reactivos
        }

        exception_events = Iso45001CambioCaptura.query.filter_by(
            evaluacion_id=evaluation.id,
            entidad_tipo="punto_documental",
            origen="excepcion",
        ).all()
        assert {event.punto_id for event in exception_events} >= {
            point_responses[0].id,
            point_responses[1].id,
        }


def test_iso45001_v3_closed_summary_uses_immutable_snapshot():
    app, ids = build_app()

    with app.app_context():
        evaluation_id = _create_v3_evaluation(ids, cycle_name="V3 snapshot de cierre")
        evaluation = db.session.get(Iso45001Evaluacion, evaluation_id)
        user = db.session.get(Usuario, ids["evaluator_id"])
        section = evaluation.ciclo.version.clausulas[0].apartados[0]
        result = bulk_apply_section_responses(
            evaluation,
            section.id,
            "si",
            "pendientes",
            user=user,
        )
        assert result["ok"] is True
        live_summary = summarize_iso45001_evaluation(evaluation)

        evaluation.estado = "cerrada"
        evaluation.cerrada_at = utcnow()
        snapshot = freeze_iso45001_snapshot(evaluation, user=user)
        snapshot_id = snapshot.id
        original_hash = snapshot.contenido_sha256
        db.session.commit()

        frozen_summary = summarize_iso45001_evaluation(evaluation)
        assert frozen_summary["generated_from_snapshot"] is True
        assert frozen_summary["snapshot_hash"] == original_hash
        assert frozen_summary["points"] == live_summary["points"]
        assert frozen_summary["percent"] == live_summary["percent"]
        assert snapshot.contenido["formula"] == {
            "scheme": "escala_0_1_2_v1",
            "values": {"no": 0, "parcial": 1, "si": 2},
            "maximum_points": 616,
        }
        assert len(snapshot.contenido["report_summary"]["dimensions"]) == 39
        assert snapshot.contenido["report_summary"]["capture_traceability"]

        response = evaluation.respuestas[0]
        response.calificacion = "no"
        response.valor = 0
        db.session.commit()
        db.session.expire_all()

        evaluation = db.session.get(Iso45001Evaluacion, evaluation_id)
        after_live_mutation = summarize_iso45001_evaluation(evaluation)
        assert after_live_mutation["generated_from_snapshot"] is True
        assert after_live_mutation["points"] == live_summary["points"]
        assert after_live_mutation["percent"] == live_summary["percent"]
        frozen_question = next(
            row
            for section_row in after_live_mutation["sections"]
            for row in section_row["questions"]
            if row["reactivo"].codigo == response.reactivo.codigo
        )
        assert frozen_question["selected"] == "si"
        assert freeze_iso45001_snapshot(evaluation, user=user).id == snapshot_id

        persisted_snapshot = db.session.get(Iso45001EvaluacionSnapshotCierre, snapshot_id)
        persisted_snapshot.contenido_sha256 = "0" * 64
        with pytest.raises(ValueError, match="inmutable"):
            db.session.commit()
        db.session.rollback()
        assert (
            db.session.get(Iso45001EvaluacionSnapshotCierre, snapshot_id).contenido_sha256
            == original_hash
        )
