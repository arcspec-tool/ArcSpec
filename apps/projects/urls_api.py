from django.urls import path

from apps.projects import api

urlpatterns = [
    path('search/', api.GlobalSearchView.as_view(), name='api_global_search'),

    path('<slug:slug>/sections/', api.SectionListView.as_view(), name='api_section_list'),
    path('<slug:slug>/sections/reorder/', api.SectionReorderView.as_view(), name='api_section_reorder'),

    path('<slug:slug>/items/', api.ItemListCreateView.as_view(), name='api_item_list'),
    path('<slug:slug>/items/reorder/', api.ItemReorderView.as_view(), name='api_item_reorder'),
    path('<slug:slug>/items/bulk/', api.ItemBulkOperationView.as_view(), name='api_item_bulk'),
    path('<slug:slug>/items/search/', api.ItemSearchView.as_view(), name='api_item_search'),
    path('<slug:slug>/items/<uuid:public_key>/', api.ItemRetrieveUpdateDestroyView.as_view(), name='api_item_detail'),
    path('<slug:slug>/items/<uuid:public_key>/inline-edit/', api.ItemInlineEditView.as_view(), name='api_item_inline_edit'),
    path('<slug:slug>/items/<uuid:public_key>/image/', api.ItemImageUploadView.as_view(), name='api_item_image'),

    path('<slug:slug>/items/<uuid:item_key>/comments/', api.CommentListCreateView.as_view(), name='api_comment_list'),
    path('<slug:slug>/comments/<uuid:public_key>/', api.CommentDestroyView.as_view(), name='api_comment_delete'),

    path('<slug:slug>/tags/', api.TagListView.as_view(), name='api_tag_list'),
    path('<slug:slug>/tags/create/', api.TagCreateView.as_view(), name='api_tag_create'),
    path('<slug:slug>/items/<uuid:item_key>/tags/', api.ItemTagUpdateView.as_view(), name='api_item_tags'),

    path('<slug:slug>/items/<uuid:item_key>/attachments/', api.AttachmentListCreateView.as_view(), name='api_attachment_list'),
    path('<slug:slug>/attachments/<uuid:public_key>/', api.AttachmentDestroyView.as_view(), name='api_attachment_delete'),

    path('<slug:slug>/items/<uuid:item_key>/links/', api.LinkListCreateView.as_view(), name='api_link_list'),
    path('<slug:slug>/links/<uuid:public_key>/', api.LinkDestroyView.as_view(), name='api_link_delete'),

    path('<slug:slug>/saved-views/', api.SavedViewListCreateView.as_view(), name='api_saved_view_list'),
    path('<slug:slug>/saved-views/<uuid:public_key>/', api.SavedViewDestroyView.as_view(), name='api_saved_view_delete'),

    path('<slug:slug>/preferences/', api.MemberPreferencesView.as_view(), name='api_member_preferences'),

    path('<slug:slug>/attributes/', api.ProjectAttributeListCreateView.as_view(), name='api_project_attribute_list'),
    path('<slug:slug>/attributes/<uuid:public_key>/', api.ProjectAttributeUpdateDeleteView.as_view(), name='api_project_attribute_detail'),

    path('<slug:slug>/collaborators/', api.CollaboratorListView.as_view(), name='api_collaborator_list'),
    path('<slug:slug>/collaborators/invite/', api.CollaboratorInviteView.as_view(), name='api_collaborator_invite'),
    path('<slug:slug>/collaborators/<uuid:public_key>/', api.CollaboratorUpdateView.as_view(), name='api_collaborator_update'),

    path('<slug:slug>/versions/', api.VersionListView.as_view(), name='api_version_list'),
    path('<slug:slug>/versions/<uuid:public_key>/restore/', api.VersionRestoreView.as_view(), name='api_version_restore'),

    path('<slug:slug>/audit-log/', api.AuditLogListView.as_view(), name='api_audit_log'),
]
