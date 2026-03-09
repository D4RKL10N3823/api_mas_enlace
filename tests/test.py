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