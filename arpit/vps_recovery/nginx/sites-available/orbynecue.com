server {
    server_name orbynecue.com www.orbynecue.com;

    root /var/www/orbynecue/frontend;
    index index.html;

    # ---------- FRONTEND ----------
    location / {
        try_files $uri $uri/ =404;
    }

    # ---------- BACKEND API ----------
    location /orbyneai/api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # ---------- STRIPE WEBHOOK ----------
    location /orbyneai/webhook {
        proxy_pass http://127.0.0.1:8000/webhook;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
    }


    listen 443 ssl; # managed by Certbot
    ssl_certificate /etc/letsencrypt/live/orbynecue.com/fullchain.pem; # managed by Certbot
    ssl_certificate_key /etc/letsencrypt/live/orbynecue.com/privkey.pem; # managed by Certbot
    include /etc/letsencrypt/options-ssl-nginx.conf; # managed by Certbot
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem; # managed by Certbot


}
server {
    if ($host = www.orbynecue.com) {
        return 301 https://$host$request_uri;
    } # managed by Certbot


    if ($host = orbynecue.com) {
        return 301 https://$host$request_uri;
    } # managed by Certbot


    server_name orbynecue.com www.orbynecue.com;
    listen 80;
    return 404; # managed by Certbot




}