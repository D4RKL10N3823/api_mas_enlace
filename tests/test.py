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


class TestUsuarioIntegration:
    """Tests de integración para flujo completo de usuario"""
    
    def test_complete_usuario_lifecycle(self, client, db_session):
        """Test del ciclo de vida completo de un usuario"""
        # 1. Crear usuario
        usuario_data = {
            "nombre": "Integración",
            "apellidos": "Test",
            "matricula": "2024999",
            "password": "integration123",
            "carrera": "Ingeniería en TI",
            "cuatrimestre": 1
        }
        
        response = client.post("/usuarios/", json=usuario_data)
        assert response.status_code == 201
        usuario_id = response.json()["id"]
        
        # 2. Login (para obtener token)
        from services.auth_service import AuthService
        token = create_access_token(data={"sub": "2024999"})
        headers = {"Authorization": f"Bearer {token}"}
        
        # Obtener el usuario para mockear auth
        usuario = db_session.query(Usuario).filter(
            Usuario.id == usuario_id
        ).first()
        
        def override_get_current_user():
            return usuario
        
        app.dependency_overrides[get_current_user] = override_get_current_user
        
        # 3. Obtener usuario por ID
        response = client.get(f"/usuarios/{usuario_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["matricula"] == "2024999"
        
        # 4. Actualizar usuario
        update_data = {"cuatrimestre": 2}
        response = client.put(
            f"/usuarios/{usuario_id}",
            json=update_data,
            headers=headers
        )
        assert response.status_code == 200
        assert response.json()["cuatrimestre"] == 2
        
        # 5. Eliminar usuario
        response = client.delete(f"/usuarios/{usuario_id}", headers=headers)
        assert response.status_code == 200
        
        # 6. Verificar que no existe
        response = client.get(f"/usuarios/{usuario_id}", headers=headers)
        assert response.status_code == 404
        
        app.dependency_overrides.clear()
