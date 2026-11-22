from django.urls import path

from . import views as v

urlpatterns = [
    path("rules/", v.RulesView.as_view(), name="localtax-rules"),
    path("rules/<str:ya>/", v.RulesView.as_view(), name="localtax-rules-year"),
    path("rules/<str:ya>/review/", v.RuleReviewView.as_view(), name="localtax-rules-review"),
    path("rules/<str:ya>/review/check/", v.RuleCheckView.as_view(), name="localtax-rules-check"),
    path("rules/<str:ya>/fields/", v.ReturnFieldReviewView.as_view(), name="localtax-rules-fields"),
    path("drive-account/", v.DriveAccountView.as_view(), name="localtax-drive-account"),
    path("tasks/<str:key>/", v.EngagementView.as_view(), name="localtax-engagement"),
    path("tasks/<str:key>/documents/", v.DocumentsView.as_view(), name="localtax-documents"),
    path("tasks/<str:key>/drive/", v.DriveLinkView.as_view(), name="localtax-drive"),
    path("tasks/<str:key>/drive/sync/", v.DriveSyncView.as_view(), name="localtax-drive-sync"),
    path("tasks/<str:key>/prefill/<str:step>/", v.PrefillView.as_view(), name="localtax-prefill"),
    path("tasks/<str:key>/suggestions/<int:pk>/decide/", v.SuggestionDecideView.as_view(), name="localtax-suggestion-decide"),
    path("tasks/<str:key>/flags/<int:pk>/resolve/", v.FlagResolveView.as_view(), name="localtax-flag-resolve"),
    path("tasks/<str:key>/tb/", v.TrialBalanceView.as_view(), name="localtax-tb"),
    path("tasks/<str:key>/tb/upload/", v.TrialBalanceUploadView.as_view(), name="localtax-tb-upload"),
    path("tasks/<str:key>/tb/<str:code>/", v.TbLineView.as_view(), name="localtax-tb-line"),
    path("tasks/<str:key>/adjustments/", v.AdjustmentListView.as_view(), name="localtax-adjustments"),
    path("tasks/<str:key>/adjustments/<int:pk>/", v.AdjustmentDetailView.as_view(), name="localtax-adjustment"),
    path("tasks/<str:key>/adjustments/<int:pk>/decide/", v.AdjustmentDecideView.as_view(), name="localtax-adjustment-decide"),
    path("tasks/<str:key>/reverse/effect/", v.ReverseEffectView.as_view(), name="localtax-reverse-effect"),
    path("tasks/<str:key>/stages/<str:stage>/", v.StageView.as_view(), name="localtax-stage"),
    path("tasks/<str:key>/events/", v.EventsView.as_view(), name="localtax-events"),
    path("tasks/<str:key>/messages/", v.MessagesView.as_view(), name="localtax-messages"),
    path("tasks/<str:key>/extractions/<int:pk>/decide/", v.ExtractionDecideView.as_view(), name="localtax-extraction-decide"),
    path("tasks/<str:key>/export/<str:doc>.<str:fmt>", v.ExportView.as_view(), name="localtax-export"),
    path("tasks/<str:key>/ai/<str:agent>/", v.AiView.as_view(), name="localtax-ai"),
]
