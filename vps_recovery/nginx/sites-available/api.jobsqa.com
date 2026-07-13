server {
    if ($host = api.jobsqa.com) {
        return 301 https://$host$request_uri;
    } # managed by Certbot


    listen 80;
    server_name api.jobsqa.com;
    return 301 https://$host$request_uri;


}

# HTTPS server (THIS is what Stripe will hit)
server {
    listen 443 ssl http2;
    server_name api.jobsqa.com;
    ssl_certificate /etc/letsencrypt/live/jobsqa.com/fullchain.pem; # managed by Certbot
    ssl_certificate_key /etc/letsencrypt/live/jobsqa.com/privkey.pem; # managed by Certbot

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }


}
