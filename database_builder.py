# database_builder.py
import time
from sqlalchemy import create_engine, text, make_url
from sqlalchemy.exc import OperationalError, ProgrammingError
import uuid
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
    text
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import os

# --- 1. CONFIGURACIÓN DE LA BASE DE DATOS ---
# Se recomienda usar variables de entorno para la configuración de la base de datos.
# Ejemplo de URL de conexión para PostgreSQL:
# DATABASE_URL = "postgresql://user:password@host:port/database"
DATABASE_URL = os.environ.get("DATABASE_URL")
# Declarative Base: La clase base de la cual heredarán todos los modelos (tablas).
Base = declarative_base()

# --- 2. DEFINICIÓN DE TABLAS DE ASOCIACIÓN (Muchos a Muchos) ---

# Tabla de uniión para la relación entre Transactions y Tags
transaction_tags_table = Table('transaction_tags', Base.metadata,
    Column('transaction_id', UUID(as_uuid=True), ForeignKey('transactions.transaction_id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.tag_id'), primary_key=True)
)

# Tabla de uniión para la relación entre Goals y Accounts
goal_accounts_table = Table('goal_accounts', Base.metadata,
    Column('goal_id', UUID(as_uuid=True), ForeignKey('goals.goal_id'), primary_key=True),
    Column('account_id', UUID(as_uuid=True), ForeignKey('accounts.account_id'), primary_key=True)
)


# --- 3. DEFINICIÓN DE MODELOS (TABLAS) ---

# Sección 3.1: Entidades de Definición

class Account(Base):
    """
    Representa un contenedor financiero: una cuenta bancaria, tarjeta de crédito, etc.
    Es la base para el cálculo del patrimonio neto.
    """
    __tablename__ = 'accounts'
    account_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_name = Column(String(255), unique=True, nullable=False)
    account_type = Column(Enum('Asset', 'Liability', name='account_type_enum'), nullable=False)
    currency_code = Column(String(3), nullable=False)
    initial_balance = Column(Numeric(19, 4), nullable=False)
    
    # Relaciones
    transactions = relationship("Transaction", back_populates="account")
    valuations = relationship("AssetValuationHistory", back_populates="account")

class Category(Base):
    """
    Define la taxonomía jerárquica para clasificar transacciones.
    Es el motor para el análisis de gastos e ingresos.
    """
    __tablename__ = 'categories'
    category_id = Column(Integer, primary_key=True, autoincrement=True)
    category_name = Column(String(255), unique=True, nullable=False)
    parent_category_id = Column(Integer, ForeignKey('categories.category_id'))
    purpose_type = Column(Enum('Need', 'Want', 'Savings/Goal', name='purpose_type_enum'))
    nature_type = Column(Enum('Fixed', 'Variable', name='nature_type_enum'))
    
    # Relación jerárquica (padre-hijo)
    parent = relationship('Category', remote_side=[category_id], back_populates='children')
    children = relationship('Category', back_populates='parent')

class Merchant(Base):
    """
    Normaliza la información de los comercios para evitar duplicados y
    permitir análisis por comerciante.
    """
    __tablename__ = 'merchants'
    merchant_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_name = Column(String(255), unique=True, nullable=False)
    default_category_id = Column(Integer, ForeignKey('categories.category_id'))

    # Relaciones
    default_category = relationship("Category")
    transactions = relationship("Transaction", back_populates="merchant")

class Tag(Base):
    """
    Permite el etiquetado flexible y multidimensional de transacciones
    para agrupar gastos por eventos (ej. "Vacaciones 2025").
    """
    __tablename__ = 'tags'
    tag_id = Column(Integer, primary_key=True, autoincrement=True)
    tag_name = Column(String(255), unique=True, nullable=False)

    # Relación muchos a muchos con Transaction
    transactions = relationship("Transaction", secondary=transaction_tags_table, back_populates="tags")


# Sección 3.2: Entidades de Eventos

class Transaction(Base):
    """
    El libro diario contable inmutable. Cada registro es un evento financiero
    que sigue el principio de no ser modificado ni eliminado, solo anulado o corregido.
    """
    __tablename__ = 'transactions'
    transaction_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey('accounts.account_id'), nullable=False, index=True)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey('merchants.merchant_id'), nullable=True, index=True)
    category_id = Column(Integer, ForeignKey('categories.category_id'), nullable=True, index=True)
    
    base_currency_amount = Column(Numeric(19, 4), nullable=False, comment="Monto en la divisa base del usuario. Negativo para egresos.")
    original_amount = Column(Numeric(19, 4), nullable=False)
    original_currency_code = Column(String(3), nullable=False)
    
    transaction_date = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(Enum('ACTIVE', 'VOID', 'SUPERSEDED', name='transaction_status_enum'), nullable=False, default='ACTIVE', index=True)
    
    revises_transaction_id = Column(UUID(as_uuid=True), ForeignKey('transactions.transaction_id'))
    related_transaction_id = Column(UUID(as_uuid=True), ForeignKey('transactions.transaction_id'))

    # Relaciones
    account = relationship("Account", back_populates="transactions")
    merchant = relationship("Merchant", back_populates="transactions")
    category = relationship("Category")
    splits = relationship("TransactionSplit", back_populates="transaction", cascade="all, delete-orphan")
    tags = relationship("Tag", secondary=transaction_tags_table, back_populates="transactions")

class TransactionSplit(Base):
    """ 
    Detalla las partes de una transacción dividida en múltiples categorías.
    Es una tabla hija de 'Transactions'.
    """
    __tablename__ = 'transaction_splits'
    split_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey('transactions.transaction_id'), nullable=False)
    category_id = Column(Integer, ForeignKey('categories.category_id'), nullable=False)
    amount = Column(Numeric(19, 4), nullable=False)

    # Relaciones
    transaction = relationship("Transaction", back_populates="splits")
    category = relationship("Category")

# Sección 3.3: Entidades de Seguimiento y Planificación

class AssetValuationHistory(Base):
    """
    Rastrea el valor histórico de activos no líquidos (propiedades, vehículos)
    para un cálculo preciso del patrimonio neto.
    """
    __tablename__ = 'asset_valuation_history'
    valuation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey('accounts.account_id'), nullable=False)
    valuation_date = Column(Date, nullable=False, index=True)
    value = Column(Numeric(19, 4), nullable=False)

    # Relaciones
    account = relationship("Account", back_populates="valuations")

class Goal(Base):
    """
    Define una meta financiera, como un fondo de emergencia o el pie para un departamento.
    """
    __tablename__ = 'goals'
    goal_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    goal_name = Column(String(255), nullable=False)
    target_amount = Column(Numeric(19, 4), nullable=False)
    target_date = Column(Date)
    
    # Relación muchos a muchos con Account
    accounts = relationship("Account", secondary=goal_accounts_table)


# Sección 3.4: Entidades de Optimización

class MonthlyCategorySummary(Base):
    """
    Tabla pre-calculada (o vista materializada) para acelerar la carga de reportes.
    Debe ser actualizada por un proceso batch nocturno.
    """
    __tablename__ = 'monthly_category_summary'
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    category_id = Column(Integer, ForeignKey('categories.category_id'), nullable=False)
    total_amount = Column(Numeric(19, 4), nullable=False)
    transaction_count = Column(Integer, nullable=False)

    # Clave primaria compuesta
    __table_args__ = (
        PrimaryKeyConstraint('year', 'month', 'category_id'),
    )
    
    category = relationship("Category")

# --- Sección 3.5: NUEVA SECCIÓN PARA LA MEMORIA DEL AGENTE ---

class Memory(Base):
    """
    Almacena la memoria a largo plazo del Agente de IA.
    Guarda hechos y preferencias clave sobre el usuario para personalizar interacciones futuras.
    """
    __tablename__ = 'agent_memory'
    memory_id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Podríamos usar el número de teléfono del usuario o un ID fijo,
    # ya que por ahora solo hay un usuario.
    user_id = Column(String(255), nullable=False, default='default_user', index=True)
    
    memory_text = Column(String, nullable=False, comment="El hecho o preferencia a recordar.")
    
    # Usamos server_default para que la base de datos gestione la fecha de creación.
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# --- 4. EJECUCIÓN DEL SCRIPT ---
def setup_database():
    """
    Asegura que la base de datos exista y luego crea el esquema de tablas.
    """
    # Lee la variable de entorno
    if not DATABASE_URL:
        print("❌ Error: La variable de entorno DATABASE_URL no está configurada.")
        return
    
    # Parsea la URL para obtener sus partes
    db_url_obj = make_url(DATABASE_URL)
    server_url = db_url_obj.set(database=None)
    db_name = db_url_obj.database

    # Bucle de espera para la base de datos
    for i in range(5):
        try:
            engine = create_engine(server_url)
            with engine.connect() as conn:
                print("✅ Conexión al servidor de base de datos exitosa.")
                break
        except OperationalError:
            print(f"⏳ Esperando al servidor de base de datos... (intento {i+1}/5)")
            time.sleep(2)