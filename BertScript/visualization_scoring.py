"""Pure Stage 4 scoring display policies; no Dash, pandas or runtime state.

Preserve the legacy threshold comparisons, labels and rating arithmetic.
"""


def rating_stars(score_sum, score_mean):
    return '⭐'*(min(score_sum//1000,5)+min((score_mean-100)//50,3)*2)


def score_sum_interval(score):
    return (
        'G7. 5000+' if score >= 5000 else (
        'G6. 4000~5000' if score >= 4000 else (
        'G5. 3000~3999' if score >= 3000 else (
        'G4. 2000~2999' if score >= 2000 else (
        'G3. 1000~1999' if score >= 1000 else (
        'G2. 500~999' if score>=500 else (
        'G1. 0~499' if score>=0 else (
        'B3. -500~-1' if score>= -500 else (
        'B2. -2000~-501' if score>=-2000 else
        'B1. <-2000'
        ))))))))
    )


def score_mean_interval(score):
    return (
        'G9. 500+' if score >= 500 else (
        'G8. 300~499' if score >= 300 else (
        'G7. 200~299' if score >= 200 else (
        'G6. 170~200' if score >= 170 else (
        'G5. 130~170' if score >= 130 else (
        'G4. 100~130' if score >= 100 else (
        'G3. 70~100' if score >= 70 else (
        'G2. 40~70' if score >= 40 else (
        'G1. 0~40' if score>=0 else (
        'B4. -50~0' if score>= -50 else (
        'B3. -100~-50' if score>= -100 else (
        'B2. -200~-100' if score>= -200 else (
        'B1. <-200'
        ))))))))))))
    )
