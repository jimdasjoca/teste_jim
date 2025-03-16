from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, Column, String, Float, Date, select
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import requests
import matplotlib.pyplot as plt
import pandas as pd
from datetime import datetime, timedelta
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request


# Inicializa a aplicação FastAPI
app = FastAPI()


app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Configuração do banco de dados SQLite
DATABASE_URL = "sqlite:///./test.db"
Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Definição do modelo do banco de dados
class Cotacao(Base):
    __tablename__ = "cotacoes"
    date = Column(Date, primary_key=True)
    moeda = Column(String, primary_key=True)
    valor = Column(Float)

# Criação das tabelas no banco de dados
Base.metadata.create_all(bind=engine)

# Função para buscar os últimos 5 dias úteis
def get_last_5_workdays():
    workdays = []
    today = datetime.today()
    while len(workdays) < 5:
        if today.weekday() < 5:  # Segunda a sexta (0 a 4)
            workdays.append(today.strftime("%Y-%m-%d"))
        today -= timedelta(days=1)
    return workdays[::-1]  # Retorna do mais antigo para o mais recente

# Função para buscar e armazenar cotações
def fetch_and_store_cotacoes(base="USD", moedas=["BRL", "EUR", "JPY"]):
    session = SessionLocal()
    workdays = get_last_5_workdays()

    for day in workdays:
        url = f"https://api.vatcomply.com/rates?base={base}&date={day}"
        response = requests.get(url)
        if response.status_code != 200:
            continue  # Pula se houver erro

        data = response.json()
        rates = data.get("rates", {})

        for moeda in moedas:
            if moeda in rates:
                cotacao = Cotacao(date=datetime.strptime(day, "%Y-%m-%d"), moeda=moeda, valor=rates[moeda])
                session.merge(cotacao)  # Atualiza ou insere
    session.commit()
    session.close()

# Chamar fetch_and_store_cotacoes automaticamente ao iniciar o app
@app.on_event("startup")
def startup_event():
    fetch_and_store_cotacoes()

# Endpoint para gerar o gráfico
@app.get("/grafico")
def plotar_grafico():
    session = SessionLocal()
    stmt = select(Cotacao)
    cotacoes = session.execute(stmt).scalars().all()
    session.close()
    
    if not cotacoes:
        raise HTTPException(status_code=404, detail="Nenhuma cotação encontrada.")

    df = pd.DataFrame([(c.date, c.moeda, c.valor) for c in cotacoes], columns=["date", "moeda", "valor"])
    df['date'] = pd.to_datetime(df['date'])

    plt.figure(figsize=(10, 6))
    for moeda in df['moeda'].unique():
        df_moeda = df[df['moeda'] == moeda]
        plt.plot(df_moeda['date'], df_moeda['valor'], label=moeda)
    plt.xlabel("Data")
    plt.ylabel("Valor")
    plt.title("Cotações dos últimos 5 dias úteis (com base no dólar)")
    plt.legend()
    plt.savefig("templates/grafico.png")
    plt.close()

    return {"message": "Gráfico gerado em templates/grafico.png"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
