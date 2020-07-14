import click

from ckan_cloud_operator import logs

from . import manager


@click.group()
def gcloud():
    """Manage a Gcloud cluster"""
    pass


@gcloud.command()
@click.option('--interactive', is_flag=True)
def initialize(interactive):
    manager.initialize(interactive)
    logs.exit_great_success()


@gcloud.command()
def create_storage_class():
    manager.create_storage_class()
    logs.exit_great_success()
