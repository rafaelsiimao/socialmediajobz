import pytest
from django.urls import reverse

from apps.composer.models import Post
from apps.members.models import WorkspaceMembership
from apps.workspaces.models import Workspace


@pytest.mark.django_db
def test_saved_draft_without_channel_appears_in_both_lists(client, org_owner, organization):
    workspace = Workspace.objects.create(organization=organization, name="Draft workspace")
    WorkspaceMembership.objects.create(
        user=org_owner, workspace=workspace, workspace_role=WorkspaceMembership.WorkspaceRole.OWNER
    )
    client.force_login(org_owner)
    kwargs = {"workspace_id": workspace.id}
    caption = "Draft without a connected social account"
    response = client.post(
        reverse("composer:save_post", kwargs=kwargs),
        {"caption": caption, "action": "save_draft"},
    )
    assert response.status_code == 302
    draft = Post.objects.get(workspace=workspace, caption=caption)
    assert draft.platform_posts.count() == 0
    response = client.get(reverse("composer:drafts_list", kwargs=kwargs))
    assert caption.encode() in response.content
    response = client.get(reverse("calendar:publish_tab_drafts", kwargs=kwargs))
    assert caption.encode() in response.content
    response = client.get(
        reverse("composer:preview", kwargs=kwargs),
        {"caption": caption, "_autosave_post_id": str(draft.id)},
    )
    assert caption.encode() in response.content
    assert "Prévia do conteúdo".encode() in response.content or b"Content preview" in response.content
