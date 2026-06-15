FROM python:3.12-slim
WORKDIR /app
COPY . .
EXPOSE 8787
CMD ["python", "app.py", "--host", "0.0.0.0", "--port", "8787"]
