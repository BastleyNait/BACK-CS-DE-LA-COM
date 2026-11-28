"""Web Push: envío solo tras confirmar, nunca tras revertir, y limpieza de suscripciones retiradas."""
import unittest
from unittest.mock import patch
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.core.notices import add_notice
from app.db.session import Base
from app.models.models import SuscripcionPush, User, RoleEnum
from app.routers import push


class FakeResponse:
    def __init__(self, status_code): self.status_code = status_code


class PushTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        self.student = User(id='alumno', nombres='A', apellidos='B', email='a@unsa.edu.pe', role=RoleEnum.ALUMNO, hashed_password='x')
        self.db.add(self.student); self.db.commit()
        self.keys = patch.multiple(settings, VAPID_PUBLIC_KEY='publica-ficticia', VAPID_PRIVATE_KEY=SecretStr('privada-ficticia'))
        self.keys.start()
        body = push.Subscription(endpoint='https://push.example.test/abc1234567890', keys=push.Keys(p256dh='p' * 40, auth='a' * 16))
        push.suscribir(body, self.db, self.student)

    def tearDown(self):
        self.keys.stop(); self.db.close(); self.engine.dispose()

    def notice(self):
        add_notice(self.db, 'alumno', 'evento-1', 'TAREA_ASIGNADA', 'Nueva tarea', 'Informe', {'tipo': 'TAREA', 'aulaId': 'a', 'tareaId': 't'})

    def test_sends_after_commit_with_target_url(self):
        with patch('pywebpush.webpush') as sender:
            self.notice()
            sender.assert_not_called()
            self.db.commit()
        sender.assert_called_once()
        self.assertIn('/tarea?aulaId=a&tareaId=t', sender.call_args.args[1])

    def test_rollback_discards_pending_push(self):
        with patch('pywebpush.webpush') as sender:
            self.notice(); self.db.rollback(); self.db.commit()
        sender.assert_not_called()

    def test_gone_subscription_is_removed(self):
        from pywebpush import WebPushException
        with patch('pywebpush.webpush', side_effect=WebPushException('gone', response=FakeResponse(410))):
            self.notice(); self.db.commit()
        self.assertEqual(self.db.query(SuscripcionPush).count(), 0)

    def test_capabilities_and_unsubscribe(self):
        self.assertEqual(push.capacidades(), {'web': True, 'clave': 'publica-ficticia'})
        push.dar_baja(push.Unsubscribe(endpoint='https://push.example.test/abc1234567890'), self.db, self.student)
        self.assertEqual(self.db.query(SuscripcionPush).count(), 0)
        with patch.object(settings, 'VAPID_PUBLIC_KEY', ''):
            self.assertEqual(push.capacidades(), {'web': False, 'clave': None})


if __name__ == '__main__':
    unittest.main()
