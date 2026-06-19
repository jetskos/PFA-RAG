def notifications(request):
    """
    Context processor exposant le nombre de notifications non lues 
    et les notifications récentes sur toutes les pages pour les utilisateurs connectés.
    """
    if request.user.is_authenticated:
        count = request.user.notifications.filter(lu=False).count()
        recent = request.user.notifications.all()[:5]
        return {
            'unread_notifications_count': count,
            'recent_notifications': recent
        }
    return {
        'unread_notifications_count': 0,
        'recent_notifications': []
    }

