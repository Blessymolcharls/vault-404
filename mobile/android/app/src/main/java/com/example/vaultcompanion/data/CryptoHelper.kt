package com.example.vaultcompanion.data

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.Signature
import android.util.Base64

object CryptoHelper {
    private const val KEY_ALIAS = "VaultPhoneAuthKey"
    private const val ANDROID_KEYSTORE = "AndroidKeyStore"

    fun getOrCreatePublicKey(): String {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        
        if (!keyStore.containsAlias(KEY_ALIAS)) {
            val keyPairGenerator = KeyPairGenerator.getInstance(
                KeyProperties.KEY_ALGORITHM_EC, ANDROID_KEYSTORE
            )
            keyPairGenerator.initialize(
                KeyGenParameterSpec.Builder(
                    KEY_ALIAS,
                    KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY
                )
                .setDigests(KeyProperties.DIGEST_SHA256)
                // In a production app, setUserAuthenticationRequired(true) is used to tie 
                // the key to BiometricPrompt. For this example, we keep it simple.
                .build()
            )
            keyPairGenerator.generateKeyPair()
        }

        val publicKey = keyStore.getCertificate(KEY_ALIAS).publicKey
        return Base64.encodeToString(publicKey.encoded, Base64.NO_WRAP)
    }

    fun signChallenge(challengeHex: String): String {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        val privateKey = keyStore.getKey(KEY_ALIAS, null) as java.security.PrivateKey
        
        val signature = Signature.getInstance("SHA256withECDSA").apply {
            initSign(privateKey)
            update(challengeHex.toByteArray(Charsets.UTF_8))
        }
        
        val sigBytes = signature.sign()
        return Base64.encodeToString(sigBytes, Base64.NO_WRAP)
    }
}
