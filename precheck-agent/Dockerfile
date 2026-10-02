FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY precheck_agent ./precheck_agent
COPY skills ./skills
ENV PRECHECK_SKILLS_DIR=/app/skills
EXPOSE 8100
CMD ["uvicorn", "precheck_agent.api:app", "--host", "0.0.0.0", "--port", "8100"]
