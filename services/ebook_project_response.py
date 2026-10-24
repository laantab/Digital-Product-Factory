"""Small navigation responses; stored books and dedicated previews stay intact."""


def navigation_project(project: dict) -> dict:
    data = project.get('data')
    if not isinstance(data, dict) or not (
        data.get('ebook_project_workspace') or isinstance(data.get('ebook_workspace'), dict)
    ):
        return project
    # The customer UI routes these records to /ebook-workspace/<id> instead
    # of rendering their inline HTML. Do not copy or re-encode those images.
    result = dict(project)
    slim = dict(data)
    for key in ('preview_html', 'ebook_preview_html'):
        if key in slim:
            slim[key] = ''
    review = slim.get('release_review')
    if isinstance(review, dict):
        review = dict(review)
        if isinstance(review.get('base'), dict):
            base = dict(review['base'])
            if isinstance(base.get('visuals'), list):
                base['visuals'] = [
                    {k: v for k, v in visual.items() if k not in ('thumb_b64', 'thumb')}
                    if isinstance(visual, dict) else visual
                    for visual in base['visuals']
                ]
            review['base'] = base
        slim['release_review'] = review
    result['data'] = slim
    return result
