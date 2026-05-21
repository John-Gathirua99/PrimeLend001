class Solution{
    public int solution(int N) {
        String binary = Integer.toBinaryString(N);

        int longestGap = 0;
        int currentGap = 0;
        boolean started = false;

        for (int i = 0; i < binary.length(); i++) {
            char digit = binary.charAt(i);

            if (digit == '1') {
                if (started) {
                    longestGap = Math.max(longestGap, currentGap);
                }
                started = true;
                currentGap = 0;
            } else if (started) {
                currentGap++;
            }
        }

        return longestGap;
    }
}