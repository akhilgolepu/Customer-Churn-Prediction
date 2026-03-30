export interface Prediction {
    predictionId: string;
    probability: number;
    isChurn: boolean;
    shadowProbability?: number;
    timestamp: number;
}




