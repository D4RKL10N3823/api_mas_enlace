import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import Mock, patch
from database import Base, get_db
from main import app
from models.usuario import Usuario
from utils.security import get_password_hash, create_access_token
from dependencies import get_current_user


SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    """
    Fixture que crea una sesión de base de datos de prueba
    """
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    """
    Fixture que crea un cliente de prueba de FastAPI
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()


@pytest.fixture
def test_usuario(db_session):
    """
    Fixture que crea un usuario de prueba en la base de datos
    """
    usuario = Usuario(
        nombre="Juan",
        apellidos="Pérez",
        matricula="2024001",
        password_hash=get_password_hash("password123"),
        carrera="Ingeniería en Software",
        cuatrimestre=5
    )
    db_session.add(usuario)
    db_session.commit()
    db_session.refresh(usuario)
    return usuario


@pytest.fixture
def test_usuario2(db_session):
    """
    Fixture que crea un segundo usuario de prueba
    """
    usuario = Usuario(
        nombre="María",
        apellidos="González",
        matricula="2024002",
        password_hash=get_password_hash("password456"),
        carrera="Ingeniería Industrial",
        cuatrimestre=3
    )
    db_session.add(usuario)
    db_session.commit()
    db_session.refresh(usuario)
    return usuario


@pytest.fixture
def auth_headers(test_usuario):
    """
    Fixture que crea headers de autenticación con un token válido
    """
    token = create_access_token(data={"sub": test_usuario.matricula})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_auth_user(test_usuario):
    """
    Fixture que mockea la autenticación devolviendo siempre el test_usuario
    """
    def override_get_current_user():
        return test_usuario
    
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield test_usuario
    app.dependency_overrides.clear()