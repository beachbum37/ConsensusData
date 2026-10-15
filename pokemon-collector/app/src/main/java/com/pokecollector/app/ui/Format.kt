package com.pokecollector.app.ui

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.pokecollector.app.PokeCollectorApp
import com.pokecollector.app.data.CardRepository
import java.text.NumberFormat
import java.util.Currency
import java.util.Locale

private val usd = NumberFormat.getCurrencyInstance(Locale.US)
private val eur = NumberFormat.getCurrencyInstance(Locale.US).apply { currency = Currency.getInstance("EUR") }

fun Double?.usd(): String = this?.let { usd.format(it) } ?: "—"
fun Double?.eur(): String = this?.let { eur.format(it) } ?: "—"

val Context.repository: CardRepository get() = (applicationContext as PokeCollectorApp).repository

@Composable
inline fun <reified VM : ViewModel> repoViewModelFactory(
    crossinline create: (CardRepository) -> VM,
): ViewModelProvider.Factory {
    val repo = LocalContext.current.repository
    return viewModelFactory { initializer { create(repo) } }
}
