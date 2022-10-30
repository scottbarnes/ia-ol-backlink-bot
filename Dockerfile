FROM thehale/python-poetry:1.2.2-py3.10-slim
WORKDIR /code
COPY . .
RUN poetry install --no-root --without=dev
CMD ["poetry", "run", "python", "ia_ol_backlink_bot/main.py"]
