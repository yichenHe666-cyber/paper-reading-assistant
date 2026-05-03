FROM python:3.11-slim

WORKDIR /app

RUN useradd -m -s /bin/bash reader
USER reader

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000 8501

CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 & streamlit run streamlit_app/main.py --server.port 8501 --server.address 0.0.0.0 --server.headless true"]
