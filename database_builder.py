# database_builder.py

import uuid
import os
import time
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Enum,
    Numeric,
    DateTime,
    Date,
    ForeignKey,
    Table,
    PrimaryKeyConstraint,
    text,
    make_url
)
from sqlalchemy.orm import declarative_base, relationship # <-- CORREGIDO
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

# --- 1. CONFIGURACIÓN DE LA BASE DE DATOS ---
DATABASE_URL = os.environ.get("DATABASE_URL")
Base = declarative_base()

# --- 2. DEFINICIÓN DE TABLAS DE ASOCIACIÓN ---
transaction_tags_table = Table('transaction_tags', Base.metadata,
    Column('transaction_id', UUID(as_uuid=True), ForeignKey('transactions.transaction_id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.tag_id'), primary_key=True)
)
goal_accounts_table = Table('goal_accounts', Base.metadata,
    Column('goal_id', UUID(as_uuid=True), ForeignKey('goals.goal_id'), primary_key=True),
    Column('account_id', UUID(as_uuid=True), ForeignKey('accounts.account_id'), primary_key=True)
)

# --- 3. DEFINICIÓN DE MODELOS (TABLAS) ---
class Account(Base):
    __tablename__ = 'accounts'
    account_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_name = Column(String(255), unique=True, nullable=False)
    account_type = Column(Enum('Asset', 'Liability', name='account_type_enum'), nullable=False)
    currency_code = Column(String(3), nullable=False)
    initial_balance = Column(Numeric(19, 4), nullable=False)
    transactions = relationship("Transaction", back_populates="account")
    valuations = relationship("AssetValuationHistory", back_populates="account")

class Category(Base):
    __tablename__ = 'categories'
    category_id = Column(Integer, primary_key=True, autoincrement=True)
    category_name = Column(String(255), unique=True, nullable=False)
    parent_category_id = Column(Integer, ForeignKey('categories.category_id'))
    purpose_type = Column(Enum('Need', 'Want', 'Savings/Goal', name='purpose_type_enum'))
    nature_type = Column(Enum('Fixed', 'Variable', name='nature_type_enum'))
    parent = relationship('Category', remote_side=[category_id], back_populates='children')
    children = relationship('Category', back_populates='parent')

class Merchant(Base):
    __tablename__ = 'merchants'
    merchant_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_name = Column(String(255), unique=True, nullable=False)
    default_category_id = Column(Integer, ForeignKey('categories.category_id'))
    default_category = relationship("Category")
    transactions = relationship("Transaction", back_populates="merchant")

class Tag(Base):
    __tablename__ = 'tags'
    tag_id = Column(Integer, primary_key=True, autoincrement=True)
    tag_name = Column(String(255), unique=True, nullable=False)
    transactions = relationship("Transaction", secondary=transaction_tags_table, back_populates="tags")

class Transaction(Base):
    __tablename__ = 'transactions'
    transaction_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey('accounts.account_id'), nullable=False, index=True)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey('merchants.merchant_id'), nullable=True, index=True)
    category_id = Column(Integer, ForeignKey('categories.category_id'), nullable=True, index=True)
    base_currency_amount = Column(Numeric(19, 4), nullable=False)
    original_amount = Column(Numeric(19, 4), nullable=False)
    original_currency_code = Column(String(3), nullable=False)
    transaction_date = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(Enum('ACTIVE', 'VOID', 'SUPERSEDED', name='transaction_status_enum'), nullable=False, default='ACTIVE', index=True)
    revises_transaction_id = Column(UUID(as_uuid=True), ForeignKey('transactions.transaction_id'))
    related_transaction_id = Column(UUID(as_uuid=True), ForeignKey('transactions.transaction_id'))
    account = relationship("Account", back_populates="transactions")
    merchant = relationship("Merchant", back_populates="transactions")
    category = relationship("Category")
    splits = relationship("TransactionSplit", back_populates="transaction", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary=transaction_tags_table, back_populates="transactions")

class TransactionSplit(Base):
    __tablename__ = 'transaction_splits'
    split_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey('transactions.transaction_id'), nullable=False)
    category_id = Column(Integer, ForeignKey('categories.category_id'), nullable=False)
    amount = Column(Numeric(19, 4), nullable=False)
    transaction = relationship("Transaction", back_populates="splits")
    category = relationship("Category")

class AssetValuationHistory(Base):
    __tablename__ = 'asset_valuation_history'
    valuation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey('accounts.account_id'), nullable=False)
    valuation_date = Column(Date, nullable=False, index=True)
    value = Column(Numeric(19, 4), nullable=False)
    account = relationship("Account", back_populates="valuations")

class Goal(Base):
    __tablename__ = 'goals'
    goal_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    goal_name = Column(String(255), nullable=False)
    target_amount = Column(Numeric(19, 4), nullable=False)
    target_date = Column(Date)
    accounts = relationship("Account", secondary=goal_accounts_table)

class MonthlyCategorySummary(Base):
    __tablename__ = 'monthly_category_summary'
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    category_id = Column(Integer, ForeignKey('categories.category_id'), nullable=False)
    total_amount = Column(Numeric(19, 4), nullable=False)
    transaction_count = Column(Integer, nullable=False)
    __table_args__ = (PrimaryKeyConstraint('year', 'month', 'category_id'),)
    category = relationship("Category")

class Memory(Base):
    __tablename__ = 'agent_memory'
    memory_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False, default='default_user', index=True)
    memory_text = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# --- 4. EJECUCIÓN DEL SCRIPT ---
def setup_database():
    if not DATABASE_URL:
        print("❌ Error: La variable de entorno DATABASE_URL no está configurada.")
        return

    try:
        db_url_obj = make_url(DATABASE_URL)
    except Exception as e:
        print(f"❌ Error: La DATABASE_URL ('{DATABASE_URL}') no es válida: {e}")
        return

    server_url = db_url_obj.set(database='postgres')
    db_name = db_url_obj.database

    engine = None
    for i in range(5):
        try:
            engine = create_engine(server_url)
            with engine.connect():
                print("✅ Conexión al servidor de base de datos exitosa.")
                break
        except OperationalError:
            print(f"⏳ Esperando al servidor de base de datos... (intento {i+1}/5)")
            time.sleep(3)
    else:
        print("❌ Error: No se pudo conectar al servidor de base de datos después de varios intentos.")
        if engine: engine.dispose()
        return

    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            print(f"Intentando crear la base de datos '{db_name}' si no existe...")
            conn.execute(text(f"CREATE DATABASE {db_name}"))
            print(f"✅ Base de datos '{db_name}' creada.")
    except ProgrammingError:
        print(f"ℹ️ La base de datos '{db_name}' ya existe.")
    except Exception as e:
        print(f"⚠️ Ocurrió un error inesperado al verificar/crear la base de datos: {e}")
    finally:
        if engine: engine.dispose()

    # --- Creación de Tablas ---
    engine = None
    try:
        engine = create_engine(DATABASE_URL)
        print(f"Conectando a '{db_name}' para crear las tablas...")
        Base.metadata.create_all(engine)
        print("🎉 ¡Éxito! Todas las tablas han sido creadas correctamente.")
        print(f"URL de conexión final: {engine.url.render_as_string(hide_password=True)}")
    except Exception as e:
        print(f"❌ Error al crear las tablas: {e}")
    finally:
        if engine: engine.dispose()

if __name__ == "__main__":
    setup_database()