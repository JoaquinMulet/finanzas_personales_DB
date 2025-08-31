# database_builder.py

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
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import os

# --- 1. CONFIGURACIÓN DE LA BASE DE DATOS ---
# Se recomienda usar variables de entorno para la configuración de la base de datos.
# Ejemplo de URL de conexión para PostgreSQL:
# DATABASE_URL = "postgresql://user:password@host:port/database"
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+pg8000://postgres:admin@localhost:5432/personal_finance")

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
    db_name = "personal_finance"
    # Usamos la URL base para conectar al servidor PostgreSQL (sin base de datos específica)
    # y poder crear nuestra base de datos.
    server_url = "postgresql+pg8000://postgres:admin@localhost:5432/"
    
    engine = create_engine(server_url)

    try:
        # Intentamos crear la base de datos. Usamos AUTOCOMMIT.
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            print(f"Intentando crear la base de datos '{db_name}' si no existe...")
            conn.execute(text(f"CREATE DATABASE {db_name}"))
            print(f"Base de datos '{db_name}' creada.")
    except ProgrammingError:
        # Si la base de datos ya existe, PostgreSQL arroja un error.
        # Lo capturamos y continuamos, ya que es el estado deseado.
        print(f"La base de datos '{db_name}' ya existe.")
    except Exception as e:
        print(f"Ocurrió un error inesperado al crear la base de datos: {e}")
        return # No continuar si hay un error
    finally:
        engine.dispose()

    # --- Creación de Tablas ---
    # Ahora nos conectamos a la base de datos recién creada/verificada.
    db_url = f"{server_url}{db_name}"
    engine = create_engine(db_url)
    try:
        print(f"Conectando a '{db_name}' para crear las tablas...")
        Base.metadata.create_all(engine)
        print("¡Éxito! Todas las tablas han sido creadas correctamente.")
        print(f"URL: {engine.url}")
    except Exception as e:
        print(f"Error al crear las tablas: {e}")

if __name__ == "__main__":
    # Esta función se ejecutará cuando corras el script directamente.
    setup_database()