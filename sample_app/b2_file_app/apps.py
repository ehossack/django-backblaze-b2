from django.apps import AppConfig


class B2FilesConfig(AppConfig):
    name = "b2_file_app"

    def ready(self):
        import _thread
        import sys
        from logging import getLogger
        from threading import Timer

        from django.conf import settings
        from django.dispatch import Signal

        logger = getLogger(__name__)

        if "runserver" in sys.argv:
            shutdownTime = int(settings.SECONDS_TO_RUN_APP)
            logger.debug(f"Lifecycle: {shutdownTime}")

            if shutdownTime:
                logger.warn(f"\n\n\n\nApp lifecycle of {shutdownTime} seconds configured. Will exit after.\n\n\n")

                def shutdown():
                    logger.warn("Exiting now!")
                    Signal().send("system")
                    _thread.interrupt_main()

                Timer(shutdownTime, shutdown).start()
