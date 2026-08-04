from Bio import AlignIO
from diff_match_patch import diff_match_patch

def compute_similarity_and_diff(text1, text2):
    dmp = diff_match_patch()
    dmp.Diff_Timeout = 0.0
    diff = dmp.diff_main(text1, text2, False)

    # similarity
    common_text = sum([len(txt) for op, txt in diff if op == 0])
    text_length = max(len(text1), len(text2))
    sim = common_text / text_length

    return sim, diff


alignment = AlignIO.read(open("PF18225_seed.txt"), "stockholm")
print(alignment)



print("="*50)
from Bio import pairwise2
from Bio.Seq import Seq 
seq1 = Seq("ACCGGT") 
seq2 = Seq("ACGT")
seq1 = Seq("QDBEFE")
seq2 = Seq("QDBKSTFE")
alignments = pairwise2.align.globalxx(seq1, seq2)
#test_alignments = pairwise2.align.localds(seq1, seq2, blosum62, -10, -1)
for alignment in alignments: 
    print(alignment)
    


seq1 = 'abcd'
seq2 = 'baeck'
seq1="一1111"
seq2="一11二11"
seq1=seq1*3
seq2=seq2*3
print("scores:\n")
print("seq1",seq1)
print("seq2",seq2)
from Bio import Align
aligner = Align.PairwiseAligner()
#print(aligner)
#print(aligner.score(seq1, seq2)/max(len(seq1),len(seq2)))
print("="*50)
print("diff_match_patch")
print(compute_similarity_and_diff(seq1,seq2))
print(compute_similarity_and_diff(list(seq1),list(seq2)))