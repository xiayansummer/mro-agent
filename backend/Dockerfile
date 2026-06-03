FROM python:3.11-slim

WORKDIR /app

# 容器时区固定 UTC:与 DB(连接已钉死 +00:00)和应用 datetime.utcnow() 一致,
# 日志时间戳也统一,避免 naive datetime 在非 UTC 主机上被错误解释。
ENV TZ=UTC

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 以非 root 用户运行,缩小容器逃逸/RCE 后的权限面(L-8)。
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
