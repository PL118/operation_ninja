"""Envoi de la liste de courses par email (SMTP)."""

import smtplib
import ssl
from email.message import EmailMessage

from . import config


class ErreurEnvoi(Exception):
    """Levee quand l'email n'a pas pu etre envoye."""


def envoyer(destinataire, sujet, corps, html=None):
    """Envoie un email texte, avec une version HTML facultative (affichee
    par les messageries qui la gerent). Leve ErreurEnvoi en cas de probleme."""
    if not config.smtp_configure():
        raise ErreurEnvoi(
            "SMTP non configure : renseignez [smtp] hote et expediteur dans "
            "config.ini, ou les variables SMTP_HOST et SMTP_FROM."
        )

    message = EmailMessage()
    message["From"] = config.valeur("smtp", "expediteur")
    message["To"] = destinataire
    message["Subject"] = sujet
    message.set_content(corps)
    if html:
        message.add_alternative(html, subtype="html")

    hote = config.valeur("smtp", "hote")
    port = config.entier("smtp", "port", 587)
    utilisateur = config.valeur("smtp", "utilisateur")
    mot_de_passe = config.valeur("smtp", "mot_de_passe")

    # Proton Mail Bridge presente un certificat auto-signe sur 127.0.0.1 :
    # la verification par defaut le refuserait. On la desactive seulement si
    # la configuration le demande explicitement, jamais d'office.
    contexte = None
    if not config.booleen("smtp", "verifier_certificat"):
        contexte = ssl.create_default_context()
        contexte.check_hostname = False
        contexte.verify_mode = ssl.CERT_NONE

    try:
        with smtplib.SMTP(hote, port, timeout=20) as serveur:
            if config.booleen("smtp", "tls"):
                serveur.starttls(context=contexte)
            if utilisateur:
                serveur.login(utilisateur, mot_de_passe)
            serveur.send_message(message)
    except (smtplib.SMTPException, OSError) as erreur:
        raise ErreurEnvoi(f"Echec de l'envoi : {erreur}") from erreur
