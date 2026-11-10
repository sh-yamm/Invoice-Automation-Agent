# The agent and its Streamlit UI in one container (the same app Streamlit Community Cloud runs)
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PORT=8501
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/src backend/src
COPY streamlit_app.py .
COPY ui ui
COPY .streamlit .streamlit
COPY rulebook rulebook
COPY data data
COPY samples samples
# runtime data (case records, uploads, page images); mount a persistent disk here
RUN mkdir -p storage
EXPOSE 8501
# NVIDIA_API_KEY comes from the host's environment, never from the image
CMD ["sh", "-c", "streamlit run streamlit_app.py --server.port ${PORT} --server.address 0.0.0.0 --server.headless true"]
