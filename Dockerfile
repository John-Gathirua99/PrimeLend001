FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt runtime.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN PYTHONPATH=/app python manage.py collectstatic --noinput

EXPOSE 3000
CMD ["sh", "-lc", "gunicorn Ai_Loan_System.wsgi:application --bind 0.0.0.0:$PORT --workers 2"]
