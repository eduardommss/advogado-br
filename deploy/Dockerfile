# Servidor MCP advogado-br por HTTP, somente leitura e sem casos — para conector remoto (PC desligado, celular, equipe).
#   docker build -f deploy/Dockerfile -t advogado-br .      (na raiz do repositório)
#   docker run -p 8000:8000 advogado-br                       → http://localhost:8000/mcp
# A base é a da última Release; refaça o build para atualizar (ex.: semanal, junto com a Action).
FROM python:3.12-slim
ARG REPO=eduardommss/advogado-br
RUN pip install --no-cache-dir "mcp>=1.2,<3" "pypdf>=4" && useradd -m app
WORKDIR /app
COPY mcp/ mcp/
ADD https://github.com/${REPO}/releases/latest/download/leis.db.gz /data/leis.db.gz
RUN gunzip /data/leis.db.gz && chown -R app /data
ENV LEIS_DB=/data/leis.db PRECEDENTES_DB=/tmp/precedentes.db HOST=0.0.0.0 PORT=8000
USER app
EXPOSE 8000
CMD ["python", "mcp/servidor.py", "--http", "--somente-leitura"]
