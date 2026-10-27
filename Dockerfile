FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOST=0.0.0.0 PORT=8000
WORKDIR /usr/src/rdg
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY run.py ./
RUN python -c "import run; import sys; run.prepare(); import app.main; print('RDG import OK')"
EXPOSE 8000
CMD ["python", "/usr/src/rdg/run.py"]
