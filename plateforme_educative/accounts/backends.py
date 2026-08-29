"""Backends d'authentification personnalisés.

`CaseInsensitiveModelBackend` : l'identifiant est l'adresse e-mail
(`USERNAME_FIELD = 'email'`). Les claviers de téléphone mettent souvent une
majuscule au premier caractère ou proposent une saisie « corrigée », et la
comparaison `=` de SQLite est sensible à la casse. On authentifie donc via
`email__iexact` pour que « Admin@Test.local » fonctionne comme
« admin@test.local ».
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class CaseInsensitiveModelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return None

        try:
            user = UserModel._default_manager.get(
                **{f"{UserModel.USERNAME_FIELD}__iexact": username.strip()}
            )
        except UserModel.DoesNotExist:
            # Même coût de hachage que le chemin nominal (anti-timing).
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:
            # Collision de casse en base : on refuse plutôt que de deviner.
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
