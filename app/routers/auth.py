"""Acceso SSP, Google Workspace y recuperación de un solo uso."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import secrets
import smtplib
import ssl
from email.message import EmailMessage

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.models import User, IdentidadGoogle, SeguridadCuenta, RecuperacionCuenta, RoleEnum
from app.schemas.schemas import LoginRequest, LoginResponse, RecoverRequest, RecoverResponse, RegisterRequest, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def session_response(db, user):
    security = db.get(SeguridadCuenta, user.id)
    token = create_access_token({"sub": user.id, "role": user.role.value, "email": user.email,
                                 "ver": security.version if security else 0, "purpose": "access"})
    return LoginResponse(token=token, user=UserOut.model_validate(user))


@router.get("/capacidades")
def capacidades_auth():
    return {"versionAcceso": 1, "restauracion": True,
            "google": bool(settings.GOOGLE_CLIENT_IDS.strip()), "dominioGoogle": "unsa.edu.pe",
            "recuperacion": bool(settings.SMTP_HOST and settings.SMTP_FROM)}


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(401, "Correo o contraseña incorrectos.")
    return session_response(db, user)


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    if body.role != "ALUMNO":
        raise HTTPException(403, "El alta pública solo permite cuentas de alumno.")
    if len(body.password) < 10 or len(body.password.encode()) > 72 or not body.nombres or not body.apellidos:
        raise HTTPException(422, "Completa tus nombres y apellidos y usa una contraseña de al menos 10 caracteres.")
    if db.query(User).filter(User.email == body.email.lower()).first():
        raise HTTPException(409, "Ya existe una cuenta con este correo.")
    user = User(nombres=body.nombres, apellidos=body.apellidos, email=body.email.lower(),
                hashed_password=hash_password(body.password), role=RoleEnum.ALUMNO)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe una cuenta con este correo.") from None
    return UserOut.model_validate(user)


class GoogleRequest(BaseModel):
    idToken: str = Field(min_length=10, max_length=12000)
    passwordSsp: SecretStr | None = None


def verify_google(token):
    audiences = [v.strip() for v in settings.GOOGLE_CLIENT_IDS.split(",") if v.strip()]
    if not audiences:
        raise HTTPException(503, "El ingreso con Google todavía requiere configurar OAuth.")
    from google.oauth2 import id_token
    from google.auth.transport.requests import Request
    class TimedRequest(Request):
        def __call__(self, *args, **kwargs):
            kwargs["timeout"] = 10
            return super().__call__(*args, **kwargs)
    try:
        claims = id_token.verify_oauth2_token(token, TimedRequest(), audience=None)
    except ValueError:
        raise HTTPException(401, "Google no pudo verificar esta cuenta.") from None
    except Exception:
        raise HTTPException(503, "No se pudo consultar a Google. Intenta nuevamente.") from None
    if claims.get("aud") not in audiences or claims.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
        raise HTTPException(401, "El acceso de Google corresponde a otra aplicación.")
    if (claims.get("email_verified") is not True or claims.get("hd") != "unsa.edu.pe"
            or not str(claims.get("email", "")).lower().endswith("@unsa.edu.pe")
            or not isinstance(claims.get("sub"), str) or not claims["sub"]):
        raise HTTPException(403, "Selecciona tu cuenta institucional de Google @unsa.edu.pe.")
    return claims


@router.post("/google", response_model=LoginResponse)
def google_login(body: GoogleRequest, db: Session = Depends(get_db)):
    claims = verify_google(body.idToken)
    email, subject = claims["email"].lower(), claims["sub"]
    identity = db.get(IdentidadGoogle, subject)
    if identity:
        return session_response(db, db.get(User, identity.user_id))
    user = db.query(User).filter(User.email == email).with_for_update().first()
    if user and db.query(IdentidadGoogle).filter(IdentidadGoogle.user_id == user.id).first():
        raise HTTPException(409, "La cuenta SSP ya está vinculada a otra identidad de Google. Contacta a administración.")
    if user:
        if body.passwordSsp is None:
            raise HTTPException(428, "Ya existe una cuenta SSP con este correo. Confirma su contraseña SSP para vincular Google por primera vez.")
        password = body.passwordSsp.get_secret_value()
        if len(password.encode()) > 72 or not verify_password(password, user.hashed_password):
            raise HTTPException(401, "La contraseña SSP no coincide. Puedes recuperar la contraseña SSP antes de vincular Google.")
    try:
        if not user:
            user = User(email=email, nombres=str(claims.get("given_name") or claims.get("name") or email.split("@")[0])[:100],
                        apellidos=str(claims.get("family_name") or "")[:100], role=RoleEnum.ALUMNO,
                        hashed_password=hash_password(secrets.token_urlsafe(48)))
            db.add(user)
            db.flush()
        db.add(IdentidadGoogle(subject=subject, user_id=user.id))
        db.commit()
    except IntegrityError:
        db.rollback()
        identity = db.get(IdentidadGoogle, subject)
        if not identity:
            raise HTTPException(409, "La cuenta cambió mientras ingresabas. Intenta nuevamente.") from None
        user = db.get(User, identity.user_id)
    return session_response(db, user)


@router.post("/recover", response_model=RecoverResponse)
def recover(body: RecoverRequest, db: Session = Depends(get_db)):
    if not settings.SMTP_HOST or not settings.SMTP_FROM:
        raise HTTPException(503, "La recuperación requiere configurar el servicio de correo. Contacta a administración.")
    user = db.query(User).filter(User.email == body.email.lower()).with_for_update().first()
    if user:
        now = datetime.now(timezone.utc)
        recent = db.query(RecuperacionCuenta).filter(RecuperacionCuenta.user_id == user.id,
                    RecuperacionCuenta.created_at > now - timedelta(minutes=2)).first()
        if not recent:
            token = secrets.token_urlsafe(32)
            db.query(RecuperacionCuenta).filter(RecuperacionCuenta.user_id == user.id).update({"usada": 1})
            db.add(RecuperacionCuenta(digest=sha256(token.encode()).hexdigest(), user_id=user.id,
                                      vence=now+timedelta(minutes=20), created_at=now))
            message = EmailMessage()
            message["Subject"] = "Restablecer contraseña de PrácticasCC"
            message["From"], message["To"] = settings.SMTP_FROM, user.email
            message.set_content("En PrácticasCC abre ¿Olvidaste tu contraseña? → Ya tengo un código y pega este código de un solo uso. Vence en 20 minutos.\n\n" + token + "\n\nSi no lo solicitaste, ignora este correo.")
            db.commit()  # Liberar el bloqueo de la cuenta antes de contactar al servicio SMTP.
            try:
                with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
                    smtp.starttls(context=ssl.create_default_context())
                    if settings.SMTP_USER:
                        smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD.get_secret_value())
                    smtp.send_message(message)
            except Exception:
                db.rollback()
                # Respuesta uniforme: no permite descubrir cuentas por fallos de correo.
    return RecoverResponse(message="Si el correo está registrado, recibirás un código. Revisa también correo no deseado.")


class ResetRequest(BaseModel):
    codigo: str = Field(min_length=32, max_length=128)
    password: str = Field(min_length=10, max_length=72)


@router.post("/reset", response_model=RecoverResponse)
def reset_password(body: ResetRequest, db: Session = Depends(get_db)):
    if len(body.password.encode()) > 72:
        raise HTTPException(422, "La contraseña admite hasta 72 bytes UTF-8.")
    digest = sha256(body.codigo.strip().encode()).hexdigest()
    candidate = db.get(RecuperacionCuenta, digest)
    if not candidate:
        raise HTTPException(422, "El código no es válido, ya se utilizó o venció.")
    user = db.query(User).filter(User.id == candidate.user_id).with_for_update().one()
    row = db.query(RecuperacionCuenta).filter(RecuperacionCuenta.digest == digest).populate_existing().with_for_update().first()
    if not row or row.usada or row.vence.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
        raise HTTPException(422, "El código no es válido, ya se utilizó o venció.")
    user.hashed_password = hash_password(body.password)
    security = db.get(SeguridadCuenta, user.id)
    if not security:
        security = SeguridadCuenta(user_id=user.id, version=0)
        db.add(security)
    security.version += 1
    db.query(RecuperacionCuenta).filter(RecuperacionCuenta.user_id == user.id).update({"usada": 1})
    db.commit()
    return RecoverResponse(message="Contraseña actualizada. Ingresa nuevamente en tus dispositivos.")
