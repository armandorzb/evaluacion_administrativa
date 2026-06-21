# Produccion

La app puede correr como servicio separado para conservar sus rutas literales:

- Presentador: `/admin`
- Audiencia: `/join`
- Demo: `123456`

## Variables

```bash
SECRET_KEY=valor-largo-y-privado
DATABASE_URL=sqlite:////var/lib/mentimeter-live/mentimeter.sqlite3
MENTI_PROXY_FIX=true
MENTI_SOCKETIO_CORS=https://menti.187.124.148.20.sslip.io
MENTI_SEED_DEMO=true
```

En el sistema municipal, configura:

```bash
MENTI_PUBLIC_URL=https://menti.187.124.148.20.sslip.io/admin
```

Asi `/menti/` funciona como puente institucional sin ocupar el `/admin` municipal.

## Gunicorn con eventlet

```bash
gunicorn -k eventlet -w 1 'mentimeter_live_app.app:app' --bind 127.0.0.1:8300
```

## Nginx

El bloque debe soportar WebSocket:

```nginx
server {
    server_name menti.187.124.148.20.sslip.io;

    location / {
        proxy_pass http://127.0.0.1:8300;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

## Salud

```bash
curl -I http://127.0.0.1:8300/healthz
```
