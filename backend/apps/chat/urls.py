from django.urls import path

from .views import (
    ChannelArchiveView,
    ChannelDetailView,
    ChannelListCreateView,
    ChannelMarkReadView,
    ChannelMembersView,
    MessageAttachmentListCreateView,
    MessageListCreateView,
    MessageThreadRepliesView,
    create_task_from_message,
    find_or_create_dm,
    link_task_to_message,
    toggle_reaction,
)

urlpatterns = [
    path("dm/", find_or_create_dm, name="chat-dm"),
    path("channels/", ChannelListCreateView.as_view(), name="channel-list"),
    path("channels/<int:pk>/", ChannelDetailView.as_view(), name="channel-detail"),
    path("channels/<int:pk>/members/", ChannelMembersView.as_view(), name="channel-members"),
    path("channels/<int:pk>/archive/", ChannelArchiveView.as_view(), name="channel-archive"),
    path("channels/<int:pk>/mark-read/", ChannelMarkReadView.as_view(), name="channel-mark-read"),
    path("channels/<int:pk>/messages/", MessageListCreateView.as_view(), name="channel-messages"),
    path("messages/<int:pk>/replies/", MessageThreadRepliesView.as_view(), name="message-replies"),
    path("messages/<int:pk>/attachments/", MessageAttachmentListCreateView.as_view(), name="message-attachments"),
    path("messages/<int:pk>/reactions/", toggle_reaction, name="message-reactions"),
    path("messages/<int:pk>/create-task/", create_task_from_message, name="message-create-task"),
    path("messages/<int:pk>/link-task/", link_task_to_message, name="message-link-task"),
]
