"""HintSystem — enforces the 5-level ladder server-side so it can't be skipped via API calls."""


class HintSystem:
    def __init__(self, hints_by_mission):
        self.hints_by_mission = hints_by_mission

    def get_hint(self, mission_id, level, prior_max_level):
        """Returns (hint_text, new_max_level, allowed_bool)."""
        if level < 1 or level > 5:
            return "Invalid hint level. Choose 1-5.", prior_max_level, False
        if level > prior_max_level + 1:
            return (
                f"You must request hints in order. Next available level: {prior_max_level + 1}.",
                prior_max_level,
                False,
            )
        mission_hints = self.hints_by_mission.get(mission_id, {})
        text = mission_hints.get(level, "No hint available at this level.")
        new_max = max(prior_max_level, level)
        return text, new_max, True
