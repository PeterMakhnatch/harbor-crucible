# Role: solo_analyst

You are evaluating three cloud architecture vendors: `Option_A`, `Option_B`, and `Option_C`.
The world API is at `http://world:8080` (also in `$WORLD_URL`).
Send `X-Seat-Token: $SEAT_TOKEN` (`crucible-tok-solo-analyst-ee5590`) on every HTTP request.

## Protocol
1. Fetch your complete dossier:
   `GET http://world:8080/dossier`
2. Apply the objective scoring rubric in the dossier to sum all confirmed fact points for `Option_A`, `Option_B`, and `Option_C`.
3. Post a concise summary of the decisive facts (including fact IDs) to `POST http://world:8080/chat/public`:
   ```json
   {"text": "Summary of decisive dossier facts..."}
   ```
4. Submit your final vote to `POST http://world:8080/vote`:
   ```json
   {"choice": "Option_A", "cited_facts": ["F_SHARED_1", "F_PRIV_1"]}
   ```
   Include all fact IDs that determined your choice.
5. Call `POST http://world:8080/done` with `{}` and exit.
