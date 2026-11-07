"""E-mails sent by the Accounts module (Spanish, like the UI)."""

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from app.core.mail import Mail

DISPLAY_TIMEZONE = ZoneInfo("Europe/Madrid")
BODY_STYLE = (
    "font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; "
    "color: #1e293b; line-height: 1.5;"
)
BUTTON_STYLE = (
    "display: inline-block; background: #4f46e5; color: #ffffff; text-decoration: none; "
    "padding: 10px 18px; border-radius: 8px; font-weight: 600;"
)


def _format_deadline(expires_at: datetime) -> str:
    return expires_at.astimezone(DISPLAY_TIMEZONE).strftime("%d/%m/%Y a las %H:%M")


def activation_mail(*, to: str, name: str, link: str, expires_at: datetime, ttl_hours: int) -> Mail:
    greeting = f"Hola {name}," if name else "Hola,"
    deadline = _format_deadline(expires_at)
    text = f"""{greeting}

Se ha creado una cuenta en Isofactu para esta dirección de correo.

Para activarla, abre el siguiente enlace y elige tu contraseña:

{link}

El enlace caduca en {ttl_hours} horas (el {deadline}).
Si caduca, pide a tu administrador que te envíe uno nuevo.

Si no esperabas este mensaje, puedes ignorarlo.

— Isofactu
"""
    html = f"""\
<!DOCTYPE html>
<html lang="es">
  <body style="{BODY_STYLE}">
    <p>{escape(greeting)}</p>
    <p>Se ha creado una cuenta en <strong>Isofactu</strong> para esta dirección de correo.</p>
    <p>Para activarla, abre el siguiente enlace y elige tu contraseña:</p>
    <p>
      <a href="{escape(link)}" style="{BUTTON_STYLE}">
        Activar mi cuenta
      </a>
    </p>
    <p style="font-size: 13px; color: #64748b;">
      Si el botón no funciona, copia esta dirección en tu navegador:<br>
      <a href="{escape(link)}">{escape(link)}</a>
    </p>
    <p style="font-size: 13px; color: #64748b;">
      El enlace caduca en {ttl_hours} horas (el {escape(deadline)}).
      Si caduca, pide a tu administrador que te envíe uno nuevo.
    </p>
    <p style="font-size: 13px; color: #64748b;">Si no esperabas este mensaje, puedes ignorarlo.</p>
    <p>— Isofactu</p>
  </body>
</html>
"""
    return Mail(to=to, subject="Activa tu cuenta de Isofactu", text=text, html=html)
