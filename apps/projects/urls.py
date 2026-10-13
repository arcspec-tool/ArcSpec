from django.urls import path

from apps.projects import views

urlpatterns = [
    path('', views.ProjectListView.as_view(), name='project_list'),
    path('create/', views.ProjectCreateView.as_view(), name='project_create'),
    path('<slug:slug>/', views.ProjectDetailView.as_view(), name='project_detail'),
    path('<slug:slug>/edit/', views.ProjectUpdateView.as_view(), name='project_update'),
    path('<slug:slug>/archive/', views.ProjectArchiveView.as_view(), name='project_archive'),
    path('<slug:slug>/restore/', views.ProjectRestoreView.as_view(), name='project_restore'),
    path('<slug:slug>/delete/', views.ProjectDeleteView.as_view(), name='project_delete'),
    path('<slug:slug>/duplicate/', views.ProjectDuplicateView.as_view(), name='project_duplicate'),
    path('<slug:slug>/export/', views.ProjectExportView.as_view(), name='project_export'),
    path('<slug:slug>/attachments/<uuid:public_key>/download/', views.AttachmentDownloadView.as_view(), name='attachment_download'),
    path('<slug:slug>/items/<uuid:public_key>/image/', views.ItemImageView.as_view(), name='item_image'),
    path('<slug:slug>/sections/create/', views.SectionCreateView.as_view(), name='section_create'),
    path('<slug:slug>/sections/<uuid:public_key>/update/', views.SectionUpdateView.as_view(), name='section_update'),
    path('<slug:slug>/sections/<uuid:public_key>/delete/', views.SectionDeleteView.as_view(), name='section_delete'),
    path('<slug:slug>/sections/reorder/', views.SectionReorderView.as_view(), name='section_reorder'),
]
