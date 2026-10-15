package com.pokecollector.app.ui.detail

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import com.pokecollector.app.data.CardRepository
import com.pokecollector.app.data.Pricing
import com.pokecollector.app.data.api.ApiCard
import com.pokecollector.app.data.db.OwnedCard
import com.pokecollector.app.ui.eur
import com.pokecollector.app.ui.repoViewModelFactory
import com.pokecollector.app.ui.usd
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class CardDetailViewModel(private val repo: CardRepository, private val cardId: String) : ViewModel() {
    val card = MutableStateFlow<Result<ApiCard>?>(null)
    val owned = repo.owned(cardId).stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    init { load() }

    fun load() {
        card.value = null
        viewModelScope.launch { card.value = runCatching { repo.card(cardId) } }
    }

    fun add(card: ApiCard, variant: String) = viewModelScope.launch { repo.add(card, variant) }
    fun setQuantity(item: OwnedCard, qty: Int) = viewModelScope.launch { repo.setQuantity(item, qty) }
}

@Composable
fun CardDetailScreen(cardId: String) {
    val vm: CardDetailViewModel = viewModel(key = cardId, factory = repoViewModelFactory { CardDetailViewModel(it, cardId) })
    val result by vm.card.collectAsStateWithLifecycle()
    val owned by vm.owned.collectAsStateWithLifecycle()

    when (val r = result) {
        null -> Box(Modifier.fillMaxSize(), Alignment.Center) { CircularProgressIndicator() }
        else -> r.fold(
            onSuccess = { Detail(it, owned, vm) },
            onFailure = {
                Column(Modifier.fillMaxSize(), Arrangement.Center, Alignment.CenterHorizontally) {
                    Text("Couldn't load this card.")
                    Button(onClick = vm::load, Modifier.padding(top = 8.dp)) { Text("Retry") }
                }
            },
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Detail(card: ApiCard, owned: List<OwnedCard>, vm: CardDetailViewModel) {
    val context = LocalContext.current
    val variants = remember(card) { Pricing.variants(card) }
    var variant by remember(card) { mutableStateOf(Pricing.defaultVariant(card)) }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)) {
        AsyncImage(
            model = card.images.large,
            contentDescription = card.name,
            modifier = Modifier.fillMaxWidth(0.75f).align(Alignment.CenterHorizontally).clip(RoundedCornerShape(12.dp)),
        )
        Text(card.name, style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(top = 16.dp))
        Text(
            "${card.set.name} (${card.set.series}) · ${card.number}/${card.set.printedTotal}" +
                (card.rarity?.let { " · $it" } ?: ""),
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        // Market value
        Card(Modifier.fillMaxWidth().padding(vertical = 16.dp)) {
            Column(Modifier.padding(16.dp)) {
                Text("Market value", style = MaterialTheme.typography.titleMedium)
                Text(
                    Pricing.marketUsd(card, variant).usd(),
                    style = MaterialTheme.typography.displaySmall,
                    fontWeight = FontWeight.Bold,
                )
                Text("TCGplayer market · ${Pricing.label(variant)}", style = MaterialTheme.typography.bodySmall)
                if (variants.isNotEmpty()) {
                    HorizontalDivider(Modifier.padding(vertical = 12.dp))
                    PriceRow("Variant", "Low", "Market", "High", header = true)
                    variants.forEach { PriceRow(it.label, it.low.usd(), it.market.usd(), it.high.usd()) }
                } else {
                    Text("No TCGplayer price data for this card.", Modifier.padding(top = 8.dp))
                }
                Pricing.trendEur(card, variant)?.let {
                    HorizontalDivider(Modifier.padding(vertical = 12.dp))
                    Text("Cardmarket (EU) trend: ${it.eur()}", style = MaterialTheme.typography.bodyMedium)
                }
                card.tcgplayer?.updatedAt?.let {
                    Text("Prices as of $it", style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 8.dp))
                }
                card.tcgplayer?.url?.let { url ->
                    OutlinedButton(
                        onClick = { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) },
                        modifier = Modifier.padding(top = 8.dp),
                    ) { Text("View listings on TCGplayer") }
                }
            }
        }

        // Add to collection
        Text("Add to collection", style = MaterialTheme.typography.titleMedium)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(vertical = 8.dp)) {
            val options = variants.map { it.variant }.ifEmpty { listOf("normal") }
            options.forEach { v ->
                FilterChip(selected = v == variant, onClick = { variant = v }, label = { Text(Pricing.label(v)) })
            }
        }
        Button(onClick = { vm.add(card, variant) }, modifier = Modifier.fillMaxWidth()) {
            Icon(Icons.Default.Add, null)
            Text("Add ${Pricing.label(variant)}", Modifier.padding(start = 8.dp))
        }

        if (owned.isNotEmpty()) {
            Text("In your collection", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 24.dp))
            owned.forEach { item ->
                Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(Pricing.label(item.variant))
                        Text(
                            "${item.priceUsd.usd()} each · ${item.priceUsd?.let { it * item.quantity }.usd()} total",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    IconButton(onClick = { vm.setQuantity(item, item.quantity - 1) }) { Icon(Icons.Default.Remove, "Remove one") }
                    Text("${item.quantity}", style = MaterialTheme.typography.titleMedium)
                    IconButton(onClick = { vm.setQuantity(item, item.quantity + 1) }) { Icon(Icons.Default.Add, "Add one") }
                }
            }
        }
    }
}

@Composable
private fun PriceRow(a: String, b: String, c: String, d: String, header: Boolean = false) {
    val style = if (header) MaterialTheme.typography.labelMedium else MaterialTheme.typography.bodyMedium
    Row(Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
        Text(a, Modifier.weight(1.4f), style = style)
        Text(b, Modifier.width(72.dp), style = style)
        Text(c, Modifier.width(72.dp), style = style, fontWeight = if (header) null else FontWeight.SemiBold)
        Text(d, Modifier.width(72.dp), style = style)
    }
}
