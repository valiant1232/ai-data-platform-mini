FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# 1) 创建非 root 用户（uid/gid=1000）
# slim 默认没有很多用户/组，这一步能解决 “gid not found” 的 warning
RUN groupadd -g 1000 app && useradd -m -u 1000 -g 1000 -s /bin/sh app

COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app

# 2) 把工作目录权限给 app 用户
RUN chown -R app:app /app

# 3) 切换到非 root 用户运行 celery
USER app

CMD ["celery", "-A", "app.celery_app.celery", "worker", "--loglevel=INFO"]