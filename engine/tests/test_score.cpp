// RED-first sign-convention suite. Every number here is hand-computed; the point is to fix
// the delta semantics on paper before the engine exists. If these pass, the perspective
// bookkeeping (side-to-move normalization, mate mapping, White-POV boundary, best-minus-played
// delta) is correct by construction.

#include "blunder/score.hpp"
#include "catch_amalgamated.hpp"

using blunder::deltaCp;
using blunder::isMateScore;
using blunder::mateValue;
using blunder::negate;
using blunder::Score;
using blunder::whitePov;

TEST_CASE("mate mapping: closer mate => larger magnitude, sign follows side to move",
          "[score][mate]") {
    CHECK(mateValue(1) == 9999);   // we mate next move
    CHECK(mateValue(3) == 9997);
    CHECK(mateValue(-1) == -9999);  // we get mated next move
    CHECK(mateValue(-5) == -9995);

    // A mate-in-1 outweighs a mate-in-5 for the same side.
    CHECK(mateValue(1) > mateValue(5));
    CHECK(mateValue(-1) < mateValue(-5));

    CHECK(isMateScore(mateValue(10)));
    CHECK(isMateScore(mateValue(-10)));
    CHECK_FALSE(isMateScore(0));
    CHECK_FALSE(isMateScore(800));
}

TEST_CASE("cp scores clamp so they can never collide with the mate band", "[score]") {
    CHECK(Score::cp(50).value == 50);
    CHECK(Score::cp(50).mate == false);
    CHECK(Score::cp(9000).value == blunder::kMaxCp);   // clamped
    CHECK(Score::cp(-9000).value == -blunder::kMaxCp);
    CHECK_FALSE(isMateScore(Score::cp(9000).value));   // still below the mate threshold
}

TEST_CASE("mateIn carries the signed distance and the mapped value", "[score][mate]") {
    const Score m = Score::mateIn(2);
    CHECK(m.value == 9998);
    CHECK(m.mate == true);
    CHECK(m.mate_in == 2);
}

TEST_CASE("negate flips a side-to-move score to the opponent's view", "[score]") {
    CHECK(negate(Score::cp(150)).value == -150);
    const Score nm = negate(Score::mateIn(3));
    CHECK(nm.value == -9997);
    CHECK(nm.mate_in == -3);
    CHECK(nm.mate == true);
}

TEST_CASE("whitePov normalizes side-to-move evals to White's perspective", "[score]") {
    // +120 for the side to move.
    CHECK(whitePov(Score::cp(120), /*white_to_move=*/true) == 120);   // White is +120
    CHECK(whitePov(Score::cp(120), /*white_to_move=*/false) == -120);  // Black to move and better
}

// --- The five hand-computed delta positions -------------------------------------------------
// Convention recap: `best` is the eval of the position the mover faces (mover POV). After the
// move it is the opponent's turn, so the resulting position's eval is reported from the
// opponent's POV; deltaCp negates it back into the mover's POV. delta = best - played, >= 0.

TEST_CASE("delta #1 — best move loses nothing", "[score][delta]") {
    // Mover is +30; the move keeps the opponent at -30 (i.e. mover still +30).
    CHECK(deltaCp(Score::cp(+30), /*after_played=*/Score::cp(-30)) == 0);
}

TEST_CASE("delta #2 — hanging a pawn", "[score][delta]") {
    // Mover was +20; after the move the opponent is +100 (mover -100). 20 - (-100) = 120.
    CHECK(deltaCp(Score::cp(+20), Score::cp(+100)) == 120);
}

TEST_CASE("delta #3 — hanging a piece", "[score][delta]") {
    // Mover was +50; after the move the opponent is +330 (mover -330). 50 - (-330) = 380.
    CHECK(deltaCp(Score::cp(+50), Score::cp(+330)) == 380);
}

TEST_CASE("delta #4 — Black to move blunders into mate (mate + black-to-move case)",
          "[score][delta][mate]") {
    // Black (side to move) was +40. Black's move lets White mate in 1: the resulting position
    // has White to move with mate in 1, so its eval (White POV) is mateIn(1) = +9999.
    const Score best_for_black = Score::cp(+40);
    const Score after = Score::mateIn(1);  // resulting position, opponent (White) POV
    CHECK(deltaCp(best_for_black, after) == 40 + 9999);  // 10039

    // And the stored White-POV eval after the move shows White mating, not Black.
    const Score played_black_pov = negate(after);              // -9999, Black POV
    CHECK(whitePov(played_black_pov, /*white_to_move=*/false) == 9999);
}

TEST_CASE("delta #5 — converting a winning mate loses nothing (clamp + mate dominance)",
          "[score][delta][mate]") {
    // Mover has mate in 2 (best = +9998). The move forces the resulting position to mate the
    // opponent in 1: opponent POV = mateIn(-1) = -9999, so mover POV = +9999. 9998 - 9999 < 0,
    // clamped to 0 — no blunder.
    CHECK(deltaCp(Score::mateIn(2), Score::mateIn(-1)) == 0);
}

TEST_CASE("delta clamps small search noise to zero", "[score][delta]") {
    // Best said +10, the resulting position says the mover is +50 — search noise, not a gain.
    CHECK(deltaCp(Score::cp(+10), Score::cp(-50)) == 0);
}
