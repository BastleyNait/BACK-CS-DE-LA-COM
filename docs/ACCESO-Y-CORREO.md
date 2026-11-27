# Acceso institucional y correo

## Acceso por rol

- `GOOGLE_CLIENT_IDS`: Client ID web creado en un proyecto propio de Google Cloud. No hace falta administrar el dominio `unsa.edu.pe`: el backend acepta solo identidades con `hd=unsa.edu.pe`, correo `@unsa.edu.pe` y `email_verified`.
- `PASSWORD_LOGIN_ROLES`: roles que pueden ingresar con contraseña (CSV). Vacío permite todos los roles, que es el modo actual. Con Google activo se usa `SUPERVISOR`, porque los supervisores de centros externos no tienen cuenta institucional. Con la restricción activa:
  - `/auth/login` responde 403 a los demás roles con el mensaje para ingresar con Google.
  - Se cierra el registro público con contraseña.
  - La recuperación no envía códigos a esos roles.
  - La primera entrada con Google vincula la cuenta creada por administración sin pedir contraseña, porque el correo institucional verificado basta.
  - `/auth/capacidades` informa `contrasenaRoles` para que la pantalla de ingreso lo indique.
- No activar `PASSWORD_LOGIN_ROLES` sin `GOOGLE_CLIENT_IDS`: nadie salvo los supervisores podría ingresar.

## Correo con Resend

`RESEND_API_KEY` configura el SMTP de Resend (`smtp.resend.com:587`, usuario `resend`) si `SMTP_HOST` está vacío. El remitente por defecto es `onboarding@resend.dev`, y con él Resend solo entrega al correo dueño de la cuenta. Para enviar a cualquier usuario hay que verificar un dominio propio en Resend y fijar `RESEND_FROM`. No hace falta cambiar código.
