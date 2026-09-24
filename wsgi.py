"""Point d'entree WSGI pour un hebergement en ligne (PythonAnywhere...).

Le fichier WSGI de l'hebergeur ajoute ce dossier au sys.path puis fait :
    from wsgi import application
"""

from app import creer_app

application = creer_app()
