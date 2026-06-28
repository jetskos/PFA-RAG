# PFA RAG: Platforme Educative - Docker Startup Guide

This document explains how to run, stop, and manage the complete Docker setup for the educational platform.
Your environment is configured to run Django, Celery, Redis, and MySQL using Docker Compose.

## Prerequisites
- **Docker Desktop** installed and running on Windows.
- **WSL 2** enabled (this gives Docker better performance).

## Step-by-Step Execution

### 1. Start the Environment
To start the entire environment (Django, Celery Worker, MySQL Database, and Redis Broker) in detached mode, open PowerShell, navigate to the `plateforme_educative` folder, and run:
```powershell
docker-compose up -d
```
The `-d` flag means "detached" so the terminal will not be blocked.

### 2. Verify Services are Running
To check if all 4 services are running properly, use:
```powershell
docker-compose ps
```

You should see `pfarag_web`, `pfarag_celery`, `pfarag_redis`, and `pfarag_db` all marked as `Up`.

### 3. Check Logs (Debugging)
If a service is misbehaving or you just want to see its logs, run:
```powershell
# See web logs
docker-compose logs -f web

# See celery worker logs
docker-compose logs -f celery
```
The `-f` flag will "follow" the logs in real-time. Press `Ctrl+C` to exit the log view.

### 4. Admin Superuser
An initial admin superuser has already been created for you! You can log in to the Django Admin Panel or your app with:
- **Email:** `admin@example.com`
- **Password:** `admin`

If you ever need to create another superuser in the future, you can do it by running this command inside the `web` container:
```powershell
docker-compose exec -e DJANGO_SUPERUSER_PASSWORD=yourpassword web python manage.py createsuperuser --noinput --email your@email.com
```

### 5. Accessing the Application
Your app is exposed on port **8000**:
- **Application URL:** [http://localhost:8000](http://localhost:8000)

*Note: The MySQL database is exposed on port `3308` on your host machine to avoid conflicts.*

### 6. Stop the Environment
When you are done developing, you can stop all containers by running:
```powershell
docker-compose stop
```
If you want to stop the containers AND remove the network and container instances, run:
```powershell
docker-compose down
```
*(Note: Using `docker-compose down` will **not** delete your database data, as it is safely stored in a Docker Volume).*

---

## Technical Notes & Fixes Implemented
- **`.dockerignore`**: This file is critical for this project. Without it, the `venv/` folder (~6GB) was sent to the Docker daemon causing the build to stall.
- **`pymysql` Optional**: The `core/settings.py` was tweaked to gracefully fallback to `mysqlclient` if `pymysql` is absent, since `mysqlclient` is highly optimized for Docker deployments.
- **MySQL User Configuration**: We removed the `MYSQL_USER` override because `mysql:8.0` does not allow configuring the root user this way. We rely entirely on `MYSQL_ROOT_PASSWORD`.
- **Database Port**: The host port was changed to `3308:3306` because `3307` was already taken on your local machine.
