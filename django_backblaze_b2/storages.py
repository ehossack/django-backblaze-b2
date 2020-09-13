from django_backblaze_b2.storage import BackblazeB2Storage


class PublicStorage(BackblazeB2Storage):
    pass


class LoggedInStorage(BackblazeB2Storage):
    pass


class AdminStorage(BackblazeB2Storage):
    pass
