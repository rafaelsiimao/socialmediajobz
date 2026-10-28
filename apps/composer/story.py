"""Selection rules specific to Instagram Stories; other formats are unchanged."""

STORY_CONFLICT_MESSAGE = (
    "Story não pode ser combinado com Post, Reel ou outras redes na mesma publicação. "
    "Mantenha apenas contas do Instagram no formato Story ou crie outra publicação."
)


def validate_story_selection(accounts, formats):
    story_accounts = [account for account in accounts if formats.get(str(account.pk)) == "story"]
    if any(not account.is_instagram for account in story_accounts):
        raise ValueError("O formato Story está disponível somente para o Instagram.")
    if story_accounts and len(story_accounts) != len(accounts):
        raise ValueError(STORY_CONFLICT_MESSAGE)
