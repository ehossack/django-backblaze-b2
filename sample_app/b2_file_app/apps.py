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
            shutdown_time = int(settings.SECONDS_TO_RUN_APP)
            logger.debug(f"Lifecycle: {shutdown_time}")

            if shutdown_time:
                logger.warn(f"\n\n\n\nApp lifecycle of {shutdown_time} seconds configured. Will exit after.\n\n\n")

                def shutdown():
                    logger.warn("Exiting now!")
                    Signal().send("system")
                    _thread.interrupt_main()

                Timer(shutdown_time, shutdown).start()
