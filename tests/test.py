import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

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


@pytest.fixture
def test_vacante(db_session):
    """
    Fixture que crea una vacante de prueba
    """
    from models.vacante import Vacante

    vacante = Vacante(
        nombre_empresa="Empresa Test",
        datos_vacante={
            "title": "Desarrollador Backend",
            "company": "Empresa Test",
            "requirements_summary": "Python FastAPI SQL",
            "city": "Saltillo"
        }
    )
    db_session.add(vacante)
    db_session.commit()
    db_session.refresh(vacante)
    return vacante


@pytest.fixture
def test_cv(db_session, test_usuario):
    """
    Fixture que crea un CV de prueba
    """
    from models.cv import CV

    contenido_pdf = b"%PDF-1.4 contenido de prueba"

    cv = CV(
        usuario_id=test_usuario.id,
        nombre_archivo="cv_test.pdf",
        tipo="application/pdf",
        archivo=contenido_pdf
    )
    db_session.add(cv)
    db_session.commit()
    db_session.refresh(cv)
    return cv


class TestAuthLogin:
    """Tests para POST /auth/login"""

    def test_login_success(self, client, test_usuario):
        """Test iniciar sesión con credenciales válidas"""
        response = client.post(
            "/auth/login",
            data={
                "username": "2024001",   # username = matrícula
                "password": "password123"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_invalid_password(self, client, test_usuario):
        """Test iniciar sesión con contraseña incorrecta"""
        response = client.post(
            "/auth/login",
            data={
                "username": "2024001",
                "password": "incorrecta"
            }
        )

        assert response.status_code == 401
        assert "detail" in response.json()

    def test_login_usuario_inexistente(self, client):
        """Test iniciar sesión con matrícula no registrada"""
        response = client.post(
            "/auth/login",
            data={
                "username": "9999999",
                "password": "password123"
            }
        )

        assert response.status_code == 401


class TestVacantes:
    """Tests para endpoints de vacantes"""

    @patch("services.vacante_service.VacanteFeaturesService.upsert_from_vacante")
    def test_create_vacante_success(self, mock_features, client, mock_auth_user, auth_headers):
        """Test crear y guardar una vacante"""
        vacante_data = {
            "nombre_empresa": "OpenAI",
            "datos_vacante": {
                "title": "Backend Developer",
                "company": "OpenAI",
                "requirements_summary": "Python, FastAPI, SQLAlchemy",
                "city": "Saltillo"
            }
        }

        response = client.post(
            "/vacantes/",
            json=vacante_data,
            headers=auth_headers
        )

        assert response.status_code == 201
        data = response.json()
        assert data["nombre_empresa"] == "OpenAI"
        assert "id" in data

    def test_get_vacantes_general_success(self, client, test_vacante):
        """Test obtener listado general de vacantes"""
        response = client.get("/vacantes/general")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(v["nombre_empresa"] == "Empresa Test" for v in data)


class TestCV:
    """Tests para endpoints de CV"""

    @patch("services.cv_service.CVFeaturesService.upsert_from_pdf")
    def test_subir_cv_success(self, mock_cv_features, client, test_usuario, mock_auth_user, auth_headers):
        """Test subir CV en formato PDF"""
        files = {
            "archivo": ("cv_prueba.pdf", b"%PDF-1.4 contenido pdf de prueba", "application/pdf")
        }
        data = {
            "usuario_id": str(test_usuario.id)
        }

        response = client.post(
            "/cv/",
            data=data,
            files=files,
            headers=auth_headers
        )

        assert response.status_code == 201
        body = response.json()
        assert body["usuario_id"] == test_usuario.id
        assert body["nombre_archivo"] == "cv_prueba.pdf"
        assert body["tipo"] == "application/pdf"
        assert "id" in body

    def test_subir_cv_invalid_file_type(self, client, test_usuario, mock_auth_user, auth_headers):
        """Test subir archivo que no es PDF"""
        files = {
            "archivo": ("archivo.txt", b"texto plano", "text/plain")
        }
        data = {
            "usuario_id": str(test_usuario.id)
        }

        response = client.post(
            "/cv/",
            data=data,
            files=files,
            headers=auth_headers
        )

        assert response.status_code == 400
        assert "pdf" in response.json()["detail"].lower()

    def test_descargar_cv_success(self, client, test_cv, mock_auth_user, auth_headers):
        """Test descargar un CV almacenado"""
        response = client.get(
            f"/cv/descargar/{test_cv.id}",
            headers=auth_headers
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == test_cv.tipo
        assert "content-disposition" in {k.lower(): v for k, v in response.headers.items()}
        assert response.content == b"%PDF-1.4 contenido de prueba"


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


class TestGetCurrentUsuario:
    """Tests para GET /usuarios/me"""
    
    def test_get_current_usuario_success(self, client, mock_auth_user, auth_headers):
        """Test obtener usuario actual con autenticación válida"""
        response = client.get("/usuarios/me", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["matricula"] == "2024001"
        assert data["nombre"] == "Juan"
        assert data["apellidos"] == "Pérez"
        assert "password" not in data
        assert "password_hash" not in data
    
    def test_get_current_usuario_without_auth(self, client):
        """Test obtener usuario actual sin autenticación"""
        response = client.get("/usuarios/me")
        
        assert response.status_code == 401
        assert "detail" in response.json()


class TestGetAllUsuarios:
    """Tests para GET /usuarios/"""
    
    def test_get_all_usuarios_empty(self, client, mock_auth_user, auth_headers):
        """Test obtener todos los usuarios cuando la lista está vacía"""
        response = client.get("/usuarios/", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Debería tener al menos el usuario de autenticación
        assert len(data) >= 1
    
    def test_get_all_usuarios_with_data(self, client, test_usuario, test_usuario2, 
                                       mock_auth_user, auth_headers):
        """Test obtener todos los usuarios con datos"""
        response = client.get("/usuarios/", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2
        
        # Verificar que los usuarios están en la respuesta
        matriculas = [u["matricula"] for u in data]
        assert "2024001" in matriculas
        assert "2024002" in matriculas
    
    def test_get_all_usuarios_pagination(self, client, test_usuario, test_usuario2,
                                        mock_auth_user, auth_headers):
        """Test paginación de usuarios"""
        # Primera página (limit=1)
        response = client.get("/usuarios/?skip=0&limit=1", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        
        # Segunda página
        response = client.get("/usuarios/?skip=1&limit=1", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
    
    def test_get_all_usuarios_without_auth(self, client):
        """Test obtener todos los usuarios sin autenticación"""
        response = client.get("/usuarios/")
        
        assert response.status_code == 401


class TestGetUsuarioById:
    """Tests para GET /usuarios/{usuario_id}"""
    
    def test_get_usuario_by_id_success(self, client, test_usuario, 
                                      mock_auth_user, auth_headers):
        """Test obtener usuario por ID con éxito"""
        response = client.get(f"/usuarios/{test_usuario.id}", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_usuario.id
        assert data["matricula"] == "2024001"
        assert data["nombre"] == "Juan"
    
    def test_get_usuario_by_id_not_found(self, client, mock_auth_user, auth_headers):
        """Test obtener usuario que no existe"""
        response = client.get("/usuarios/99999", headers=auth_headers)
        
        assert response.status_code == 404
        assert "no encontrado" in response.json()["detail"].lower()
    
    def test_get_usuario_by_id_without_auth(self, client, test_usuario):
        """Test obtener usuario por ID sin autenticación"""
        response = client.get(f"/usuarios/{test_usuario.id}")
        
        assert response.status_code == 401


class TestCreateUsuario:
    """Tests para POST /usuarios/"""
    
    def test_create_usuario_success(self, client, db_session):
        """Test crear usuario con éxito"""
        usuario_data = {
            "nombre": "Carlos",
            "apellidos": "López",
            "matricula": "2024003",
            "password": "securepass123",
            "carrera": "Ingeniería Mecatrónica",
            "cuatrimestre": 4
        }
        
        response = client.post("/usuarios/", json=usuario_data)
        
        assert response.status_code == 201
        data = response.json()
        assert data["nombre"] == "Carlos"
        assert data["apellidos"] == "López"
        assert data["matricula"] == "2024003"
        assert data["carrera"] == "Ingeniería Mecatrónica"
        assert data["cuatrimestre"] == 4
        assert "id" in data
        assert "password" not in data
        assert "password_hash" not in data
    
    def test_create_usuario_duplicate_matricula(self, client, test_usuario):
        """Test crear usuario con matrícula duplicada"""
        usuario_data = {
            "nombre": "Pedro",
            "apellidos": "Ramírez",
            "matricula": "2024001",  # Matrícula ya existe
            "password": "password123",
            "carrera": "Ingeniería Civil",
            "cuatrimestre": 2
        }
        
        response = client.post("/usuarios/", json=usuario_data)
        
        assert response.status_code == 400
        assert "ya está registrada" in response.json()["detail"].lower()
    
    def test_create_usuario_missing_required_field(self, client):
        """Test crear usuario sin campo requerido"""
        usuario_data = {
            "nombre": "Ana",
            "apellidos": "Martínez",
            # Falta matrícula
            "password": "password123"
        }
        
        response = client.post("/usuarios/", json=usuario_data)
        
        assert response.status_code == 422  # Validation error
    
    def test_create_usuario_invalid_password(self, client):
        """Test crear usuario con contraseña muy corta"""
        usuario_data = {
            "nombre": "Luis",
            "apellidos": "Hernández",
            "matricula": "2024004",
            "password": "123",  # Muy corta (< 6 caracteres)
            "carrera": "Ingeniería en Energías Renovables"
        }
        
        response = client.post("/usuarios/", json=usuario_data)
        
        assert response.status_code == 422  # Validation error
    
    def test_create_usuario_invalid_cuatrimestre(self, client):
        """Test crear usuario con cuatrimestre inválido"""
        usuario_data = {
            "nombre": "Roberto",
            "apellidos": "Sánchez",
            "matricula": "2024005",
            "password": "password123",
            "cuatrimestre": 15  # Fuera del rango 1-12
        }
        
        response = client.post("/usuarios/", json=usuario_data)
        
        assert response.status_code == 422  # Validation error


class TestUpdateUsuario:
    """Tests para PUT /usuarios/{usuario_id}"""
    
    def test_update_usuario_success(self, client, test_usuario, 
                                   mock_auth_user, auth_headers):
        """Test actualizar usuario con éxito"""
        update_data = {
            "nombre": "Juan Carlos",
            "carrera": "Ingeniería en Sistemas",
            "cuatrimestre": 6
        }
        
        response = client.put(
            f"/usuarios/{test_usuario.id}", 
            json=update_data,
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["nombre"] == "Juan Carlos"
        assert data["carrera"] == "Ingeniería en Sistemas"
        assert data["cuatrimestre"] == 6
        # Campos no modificados deben mantenerse
        assert data["apellidos"] == "Pérez"
        assert data["matricula"] == "2024001"
    
    def test_update_usuario_partial(self, client, test_usuario, 
                                   mock_auth_user, auth_headers):
        """Test actualizar solo algunos campos del usuario"""
        update_data = {
            "cuatrimestre": 7
        }
        
        response = client.put(
            f"/usuarios/{test_usuario.id}",
            json=update_data,
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["cuatrimestre"] == 7
        # Otros campos deben mantenerse
        assert data["nombre"] == "Juan"
        assert data["apellidos"] == "Pérez"
    
    def test_update_usuario_password(self, client, test_usuario, db_session,
                                    mock_auth_user, auth_headers):
        """Test actualizar contraseña del usuario"""
        update_data = {
            "password": "newpassword456"
        }
        
        response = client.put(
            f"/usuarios/{test_usuario.id}",
            json=update_data,
            headers=auth_headers
        )
        
        assert response.status_code == 200
        # Verificar que la contraseña fue hasheada
        db_session.refresh(test_usuario)
        assert test_usuario.password_hash != "newpassword456"
    
    def test_update_usuario_not_found(self, client, mock_auth_user, auth_headers):
        """Test actualizar usuario que no existe"""
        update_data = {
            "nombre": "Inexistente"
        }
        
        response = client.put(
            "/usuarios/99999",
            json=update_data,
            headers=auth_headers
        )
        
        assert response.status_code == 404
    
    def test_update_usuario_without_auth(self, client, test_usuario):
        """Test actualizar usuario sin autenticación"""
        update_data = {
            "nombre": "Hacker"
        }
        
        response = client.put(f"/usuarios/{test_usuario.id}", json=update_data)
        
        assert response.status_code == 401
    
    def test_update_usuario_invalid_cuatrimestre(self, client, test_usuario,
                                                mock_auth_user, auth_headers):
        """Test actualizar con cuatrimestre inválido"""
        update_data = {
            "cuatrimestre": 20  # Fuera del rango
        }
        
        response = client.put(
            f"/usuarios/{test_usuario.id}",
            json=update_data,
            headers=auth_headers
        )
        
        assert response.status_code == 422  # Validation error


class TestDeleteUsuario:
    """Tests para DELETE /usuarios/{usuario_id}"""
    
    def test_delete_usuario_success(self, client, test_usuario2, db_session,
                                   mock_auth_user, auth_headers):
        """Test eliminar usuario con éxito"""
        usuario_id = test_usuario2.id
        
        response = client.delete(
            f"/usuarios/{usuario_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        assert "eliminado" in response.json()["message"].lower()
        
        # Verificar que el usuario fue eliminado
        deleted_usuario = db_session.query(Usuario).filter(
            Usuario.id == usuario_id
        ).first()
        assert deleted_usuario is None
    
    def test_delete_usuario_not_found(self, client, mock_auth_user, auth_headers):
        """Test eliminar usuario que no existe"""
        response = client.delete("/usuarios/99999", headers=auth_headers)
        
        assert response.status_code == 404
    
    def test_delete_usuario_without_auth(self, client, test_usuario):
        """Test eliminar usuario sin autenticación"""
        response = client.delete(f"/usuarios/{test_usuario.id}")
        
        assert response.status_code == 401