package com.pokecollector.app.ui.collection

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import com.pokecollector.app.data.CardRepository
import com.pokecollector.app.data.Pricing
import com.pokecollector.app.data.db.OwnedCard
import com.pokecollector.app.ui.repoViewModelFactory
import com.pokecollector.app.ui.usd
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import java.text.DateFormat
import java.util.Date

enum class SortBy(val label: String) { VALUE("Value"), RECENT("Recent"), NAME("Name") }

data class CollectionState(
    val items: List<OwnedCard> = emptyList(),
    val sort: SortBy = SortBy.VALUE,
    val refreshing: Boolean = false,
    val message: String? = null,
) {
    val totalValue get() = items.sumOf { (it.priceUsd ?: 0.0) * it.quantity }
    val totalCards get() = items.sumOf { it.quantity }
    val lastPriced get() = items.maxOfOrNull { it.priceUpdatedAt }
}

class CollectionViewModel(private val repo: CardRepository) : ViewModel() {
    private val sort = MutableStateFlow(SortBy.VALUE)
    private val status = MutableStateFlow(false to (null as String?))

    val state = combine(repo.collection, sort, status) { items, s, (busy, msg) ->
        val sorted = when (s) {
            SortBy.VALUE -> items.sortedByDescending { (it.priceUsd ?: 0.0) * it.quantity }
            SortBy.RECENT -> items.sortedByDescending { it.addedAt }
            SortBy.NAME -> items.sortedBy { it.name }
        }
        CollectionState(sorted, s, busy, msg)
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), CollectionState())

    fun sortBy(s: SortBy) { sort.value = s }

    fun refresh() {
        if (status.value.first) return
        viewModelScope.launch {
            status.value = true to null
            val msg = runCatching { repo.refreshPrices() }
                .fold({ "Updated prices for $it cards" }, { "Couldn't reach the price service" })
            status.value = false to msg
        }
    }
}

@Composable
fun CollectionScreen(onOpenCard: (String) -> Unit) {
    val vm: CollectionViewModel = viewModel(factory = repoViewModelFactory(::CollectionViewModel))
    val state by vm.state.collectAsStateWithLifecycle()

    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = 16.dp)) {
        item {
            Card(
                Modifier.fillMaxWidth().padding(16.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer),
            ) {
                Row(Modifier.padding(20.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Collection value", style = MaterialTheme.typography.labelLarge)
                        Text(
                            state.totalValue.usd(),
                            style = MaterialTheme.typography.displaySmall,
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            "${state.totalCards} cards · TCGplayer market" +
                                (state.lastPriced?.let { " · " + DateFormat.getDateInstance(DateFormat.MEDIUM).format(Date(it)) } ?: ""),
                            style = MaterialTheme.typography.bodySmall,
                        )
                        state.message?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                    }
                    if (state.refreshing) {
                        CircularProgressIndicator(Modifier.size(28.dp))
                    } else {
                        IconButton(onClick = vm::refresh, enabled = state.items.isNotEmpty()) {
                            Icon(Icons.Default.Refresh, contentDescription = "Refresh prices")
                        }
                    }
                }
            }
        }
        if (state.items.isEmpty()) {
            item {
                Box(Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
                    Text(
                        "No cards yet.\nTap Scan and point your camera at a card.",
                        textAlign = TextAlign.Center,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        } else {
            item {
                Row(Modifier.padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SortBy.entries.forEach { s ->
                        FilterChip(selected = state.sort == s, onClick = { vm.sortBy(s) }, label = { Text(s.label) })
                    }
                }
            }
            items(state.items, key = { it.rowId }) { item ->
                OwnedRow(item) { onOpenCard(item.cardId) }
                HorizontalDivider(Modifier.padding(start = 80.dp))
            }
        }
    }
}

@Composable
private fun OwnedRow(item: OwnedCard, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().clickable(onClick = onClick).padding(horizontal = 16.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        AsyncImage(
            model = item.imageSmall,
            contentDescription = item.name,
            modifier = Modifier.size(width = 52.dp, height = 72.dp).clip(RoundedCornerShape(4.dp)),
        )
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(item.name, style = MaterialTheme.typography.titleMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(
                "${item.setName} · ${item.number}/${item.setTotal}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1, overflow = TextOverflow.Ellipsis,
            )
            Text(
                "${Pricing.label(item.variant)} · ×${item.quantity} @ ${item.priceUsd.usd()}",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Text(
            item.priceUsd?.let { it * item.quantity }.usd(),
            style = MaterialTheme.typography.titleSmall,
            fontWeight = FontWeight.SemiBold,
        )
    }
}
