package com.example.vaultcompanion

import android.os.Bundle
import android.widget.Toast
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.biometric.BiometricPrompt
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.example.vaultcompanion.data.CryptoHelper
import com.example.vaultcompanion.data.VaultApi
import com.example.vaultcompanion.data.VerifyRequest
import com.example.vaultcompanion.theme.VaultCompanionTheme
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

class MainActivity : AppCompatActivity() {

    private val vaultApi by lazy {
        Retrofit.Builder()
            .baseUrl("http://10.0.2.2:8000") // Use 10.0.2.2 for Android emulator localhost
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(VaultApi::class.java)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            VaultCompanionTheme { 
                Surface(
                    modifier = Modifier.fillMaxSize(), 
                    color = MaterialTheme.colorScheme.background
                ) {
                    VaultCompanionScreen(onAuthenticate = ::startAuthentication)
                } 
            }
        }
    }

    private fun startAuthentication() {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                // 1. Fetch Challenge
                val challengeResponse = vaultApi.getChallenge()
                val challenge = challengeResponse.challenge
                
                withContext(Dispatchers.Main) {
                    showBiometricPrompt(challenge)
                }
            } catch (e: Exception) {
                e.printStackTrace()
                withContext(Dispatchers.Main) {
                    Toast.makeText(this@MainActivity, "Failed to get challenge: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    private fun showBiometricPrompt(challenge: String) {
        val executor = ContextCompat.getMainExecutor(this)
        val biometricPrompt = BiometricPrompt(this, executor,
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                    super.onAuthenticationError(errorCode, errString)
                    Toast.makeText(applicationContext, "Authentication error: $errString", Toast.LENGTH_SHORT).show()
                }

                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    super.onAuthenticationSucceeded(result)
                    // 2. Sign Challenge
                    verifyChallenge(challenge)
                }

                override fun onAuthenticationFailed() {
                    super.onAuthenticationFailed()
                    Toast.makeText(applicationContext, "Authentication failed", Toast.LENGTH_SHORT).show()
                }
            })

        val promptInfo = BiometricPrompt.PromptInfo.Builder()
            .setTitle("Vault Companion")
            .setSubtitle("Authenticate to access the Vault")
            .setNegativeButtonText("Cancel")
            .build()

        biometricPrompt.authenticate(promptInfo)
    }

    private fun verifyChallenge(challengeHex: String) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val signature = CryptoHelper.signChallenge(challengeHex)
                val publicKey = CryptoHelper.getOrCreatePublicKey()

                val request = VerifyRequest(challengeSignature = signature, publicKey = publicKey)
                val response = vaultApi.verifyChallenge(request)

                withContext(Dispatchers.Main) {
                    Toast.makeText(this@MainActivity, response.message, Toast.LENGTH_LONG).show()
                }
            } catch (e: Exception) {
                e.printStackTrace()
                withContext(Dispatchers.Main) {
                    Toast.makeText(this@MainActivity, "Failed to verify challenge: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }
    }
}

@Composable
fun VaultCompanionScreen(onAuthenticate: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(text = "Vault Companion App", style = MaterialTheme.typography.headlineMedium)
        Spacer(modifier = Modifier.height(32.dp))
        Button(onClick = onAuthenticate) {
            Text("Authenticate")
        }
    }
}
