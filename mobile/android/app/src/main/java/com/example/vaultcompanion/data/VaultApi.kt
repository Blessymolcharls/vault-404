package com.example.vaultcompanion.data

import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Body
import com.google.gson.annotations.SerializedName

data class ChallengeResponse(
    @SerializedName("challenge") val challenge: String,
    @SerializedName("expires_at") val expiresAt: String
)

data class VerifyRequest(
    @SerializedName("challenge_signature") val challengeSignature: String,
    @SerializedName("public_key") val publicKey: String
)

data class GenericResponse(
    @SerializedName("success") val success: Boolean,
    @SerializedName("message") val message: String
)

interface VaultApi {
    @GET("/api/v1/auth/phone/challenge")
    suspend fun getChallenge(): ChallengeResponse

    @POST("/api/v1/auth/phone/verify")
    suspend fun verifyChallenge(@Body request: VerifyRequest): GenericResponse
}
