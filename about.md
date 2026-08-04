# 1. Gerar a migration a partir das alterações nos modelos (autogenerate)
alembic revision --autogenerate -m "mensagem descritiva"

# 2. Aplicar (rever as alterações antes de aplicar)
alembic upgrade head
Exemplos do que usaste aqui:
alembic revision --autogenerate -m "add source_type to law_cache"
alembic upgrade head
Outros comandos úteis:
alembic current            # versão em que a BD está
alembic history            # histórico de migrations
alembic upgrade -1         # aplicar só a última
alembic downgrade -1       # reverter a última
alembic upgrade head       # aplicar todas as pendentes
Notas:
- Verifica o ficheiro gerado em alembic/versions/*.py antes de upgrade (o autogenerate pode não detetar tudo, ex.: constraints complexas).
- O env.py já lê a DATABASE_URL do .env e usa Base.metadata como target_metadata, por isso basta que os modelos estejam importados em app/models.