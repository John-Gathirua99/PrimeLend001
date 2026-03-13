from accounts.models import UserSecurityProfile

class TrackSecurityMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        if request.user.is_authenticated:

            ip = request.META.get('REMOTE_ADDR')
            device = request.META.get('HTTP_USER_AGENT')

            profile, created = UserSecurityProfile.objects.get_or_create(
    user=request.user
)


            # IP change detection
            if profile.last_ip and profile.last_ip != ip:
                profile.ip_change_count += 1

            # Device change detection
            if profile.last_device and profile.last_device != device:
                profile.device_change_count += 1

            profile.last_ip = ip
            profile.last_device = device

            if not profile.first_device:
                profile.first_device = device

            profile.save()

        return self.get_response(request)





