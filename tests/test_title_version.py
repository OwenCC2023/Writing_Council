from story_intake import bump_title_version


# --- No version present: the rewrite becomes v2 ---

def test_plain_title_gains_v2():
    assert bump_title_version("The Sforzato") == "The Sforzato v2"


def test_filename_stem_gains_v2_with_its_own_separator():
    assert bump_title_version("the_sforzato") == "the_sforzato_v2"


def test_empty_title_stays_empty():
    assert bump_title_version("") == ""


# --- Single component: straight increment ---

def test_single_component_increments():
    assert bump_title_version("The Sforzato v2") == "The Sforzato v3"


def test_single_component_increments_past_nine():
    assert bump_title_version("The Sforzato v9") == "The Sforzato v10"


def test_capital_v_is_preserved():
    assert bump_title_version("The Sforzato V2") == "The Sforzato V3"


# --- Dotted: highest-placed digit increments, the rest go to zero ---

def test_dotted_pair_zeroes_the_tail():
    assert bump_title_version("The Sforzato v2.3") == "The Sforzato v3.0"


def test_dotted_triple_zeroes_every_lower_component():
    assert bump_title_version("The Sforzato v2.3.4") == "The Sforzato v3.0.0"


def test_dotted_multi_digit_components():
    assert bump_title_version("The Sforzato v10.11") == "The Sforzato v11.0"


# --- Underscored: highest-placed digit increments, the rest are removed ---

def test_underscored_pair_drops_the_tail():
    assert bump_title_version("sforzato_v2_3") == "sforzato_v3"


def test_underscored_triple_drops_every_lower_component():
    assert bump_title_version("sforzato_v2_3_4") == "sforzato_v3"


# --- Separator handling ---

def test_dotted_tail_zeroes_even_when_attached_by_underscore():
    """The tail's own separator decides zero-vs-remove, not the one before 'v'."""
    assert bump_title_version("sforzato_v2.3") == "sforzato_v3.0"


def test_separator_before_the_version_is_preserved():
    assert bump_title_version("sforzato-v2") == "sforzato-v3"
    assert bump_title_version("The Sforzato v2") == "The Sforzato v3"


def test_version_glued_to_the_title_stays_glued():
    assert bump_title_version("sforzatov2") == "sforzatov3"


# --- Things that are not versions ---

def test_a_bare_trailing_number_is_not_a_version():
    """Blade Runner 2049 is a title, not a version."""
    assert bump_title_version("Blade Runner 2049") == "Blade Runner 2049 v2"


def test_a_version_not_at_the_end_is_not_bumped():
    assert bump_title_version("v2 Engines of Empire") == "v2 Engines of Empire v2"


def test_v_without_digits_is_not_a_version():
    assert bump_title_version("The Sforzato v") == "The Sforzato v v2"
